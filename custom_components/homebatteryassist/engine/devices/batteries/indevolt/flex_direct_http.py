"""Direct driver: Indevolt SolidFlex / PowerFlex (local API generation 2)
over its local HTTP RPC API — PREPARED, NOT USED.

Requests go to ``http://<host>:8080/rpc/<Method>`` with the JSON parameters
URL-encoded in the query string (``?config=<compact JSON>``) and no body:
``Sys.GetConfig`` (GET; device type, serial, firmware), ``Indevolt.GetData``
(POST, ``{"t": [point ids]}``, 1-50 points; the reply is keyed by the point
id as a string and may be incomplete) and ``Indevolt.SetData`` (POST,
``{"f": 16, "t": point, "v": [ints]}``, accepted when ``{"result": true}``).
The local API must be set to plain HTTP in the Indevolt app (Digest answers
401/403). The device tolerates one request at a time on a fresh connection,
at least 1 s apart (start to start; 5 s recommended), so requests are
serialised and paced here.

Battery power (point 6000) is + discharging on the wire and turned into
+ charging here. Total AC power (2278, + charging) includes the bypass port
(667); the inverter's own AC power is the difference. 9999 on the remaining
time points means "not applicable".

Control (never called while HomeBatteryAssist is read-only) only ever writes
the realtime tuple, point 47015 = [action, power W, target SoC] (RAM): STOP
``[0, 0, 0]`` first and wait for the echo, then charge ``[1, P, SoC + 5]`` or
discharge ``[2, P, SoC - 5]`` (a rolling target, so the battery stops by
itself within about 5 % when the controller disappears). Hazards:

- **every other point is stored in flash**, including the work mode
  (7101 / 47005) and the reserve, power and feed-in limits: writing them in
  a loop wears the controller out within days, so this driver can not write
  them at all;
- the work mode must be "realtime" (4), chosen by the user in the app;
- the BK1600 (generation 1 API) and unknown models must not be controlled;
- the STOP echo trails by 9-19 s and a standby unit takes 10-15 s to start;
- after a failed write the outcome is unknown (it may still have applied);
- writing competes with another integration that controls the battery.

Device facts: Omnibattery's Indevolt client and driver (GPL-3.0) as
reference for facts only (some citing Indevolt); own implementation.
"""

from __future__ import annotations

import asyncio
import json
import math
import time
from collections.abc import Awaitable, Callable, Iterable
from typing import Any

from homeassistant.helpers.aiohttp_client import async_get_clientsession

from ..base import BatteryModel, BatteryTelemetry
from ..direct.base import DirectReading
from ..direct.http_driver import HttpBatteryDriver
from .bk1600 import IndevoltBk1600
from .flex_1200 import IndevoltFlex1200
from .flex_2000 import IndevoltFlex2000
from .flex_3000 import IndevoltFlex3000
from .solidflex_3600 import IndevoltSolidFlex3600

DEFAULT_PORT = 8080
MIN_SPACING = 1.0  # s between request starts (device minimum)
MAX_POINTS = 50  # per GetData
REALTIME_POINT = 47015  # the only point that is not stored in flash
MAX_POWER_W = 10800
MIN_TARGET_SOC = 5
STOP = (0, 0, 0)
ECHO_TIMEOUT = 30.0  # s for the STOP echo
ECHO_INTERVAL = 2.0  # s between echo reads
QUIET_W = 100  # battery counts as stopped below this
NOT_APPLICABLE = 9999  # remaining time points

# Data points read every cycle (name → point id); 33 points, one request.
POINTS: dict[str, int] = {
    "model_code": 1,
    "battery_power": 6000,  # + discharging
    "battery_state": 6001,
    "soc": 6002,
    "ac_power": 2278,  # + charging, incl. bypass
    "bypass_power": 667,
    "work_mode": 7101,
    "operating_status": 11006,
    "realtime_status": 6107,
    "realtime_target_soc": 6108,
    "realtime_power": 6109,
    "pv_power": 1501,
    "grid_power": 11016,  # + import, from the paired meter
    "battery_temperature": 9012,
    "transformer_temperature": 11005,
    "cycles": 9003,
    "cell_a": 9009,
    "cell_b": 9011,
    "remaining_charge": 11019,
    "remaining_discharge": 11020,
    "charged_today": 6004,
    "discharged_today": 6005,
    "charged_total": 6006,
    "discharged_total": 6007,
    "pv_total": 1505,  # Wh
    "reserve_soc": 6105,
    "max_charge_setting": 11009,
    "max_discharge_setting": 11011,
    "discharge_limit": 11032,
    "max_charge_hw": 114,
    "max_discharge_hw": 115,
    "capacity": 142,  # kWh
    "device_mode": 606,  # may be a string
}
CONTROL_POINTS = (1, 6002, 7101, 6105, 11009, 114, 11011, 11032, 115)
ECHO_POINTS = (6107, 6000, 2278, 667)

BATTERY_STATE = {1000: "idle", 1001: "charging", 1002: "discharging"}
REALTIME_STATUS = {
    0: "standby",
    1000: "standby",
    1: "charging",
    1001: "charging",
    2: "discharging",
    1002: "discharging",
}
WORK_MODE = {0: "portable", 1: "self_consumption", 4: "realtime", 5: "schedule"}
REALTIME_MODE = 4
OPERATING_STATUS = {
    1: "off",
    2: "sleep",
    3: "starting",
    4: "mppt",
    5: "current_limiting",
    6: "shutting_down",
    7: "inverter_fault",
    8: "standby",
    9: "grid_charging",
    10: "grid_discharging",
    11: "off_grid_charging",
    12: "off_grid_discharging",
    13: "recovery_charging",
    14: "deep_sleep",
    15: "scheduled_full_charge",
    16: "off_grid_deep_sleep",
}
DEVICE_MODE = {1000: "cluster_main", 1001: "cluster_sub", 1002: "standalone"}
TYPES: tuple[type[BatteryModel], ...] = (
    IndevoltFlex1200,
    IndevoltFlex2000,
    IndevoltFlex3000,
    IndevoltSolidFlex3600,
    IndevoltBk1600,
)


def number(value: Any) -> float | None:
    """A finite JSON number or numeric string; None otherwise."""
    if isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def lowest(*values: float | None) -> float | None:
    """The lowest known value."""
    known = [v for v in values if v is not None]
    return min(known) if known else None


def code_type(code: Any) -> type[BatteryModel] | None:
    """The type of a model code (point 1)."""
    if not isinstance(code, str) or not code.strip():
        return None
    return next((t for t in TYPES if t().matches(code)), None)


def valid_realtime(values: Iterable[Any]) -> tuple[int, int, int]:
    """The realtime tuple, checked: STOP, or charge / discharge (1 / 2) with
    0-10800 W and a target SoC of 5-100 %. Anything else raises."""
    command = tuple(values)
    if len(command) != 3 or not all(
        isinstance(v, int) and not isinstance(v, bool) for v in command
    ):
        raise ValueError(f"Indevolt: realtime command must be 3 integers: {command}")
    action, power, target = command
    if command != STOP and not (
        action in (1, 2)
        and 0 <= power <= MAX_POWER_W
        and MIN_TARGET_SOC <= target <= 100
    ):
        raise ValueError(f"Indevolt: realtime command out of range: {command}")
    return action, power, target


class IndevoltHttpDriver(HttpBatteryDriver):
    """Indevolt SolidFlex / PowerFlex over the local HTTP RPC API
    (address = host[:port], port 8080 by default; option ``spacing`` in s,
    at least 1)."""

    key = "indevolt_http"
    name = "Indevolt (HTTP)"
    models = TYPES
    can_write = True  # realtime tuple only; never called
    min_interval_s = 5.0  # control: one request every few seconds at most
    source = "Omnibattery infra/indevolt_client.py, drivers/indevolt.py (facts only)"
    timeout = 5.0

    def __init__(self, hass: Any, address: str, **options: Any) -> None:
        """Initialize; one paced request at a time per battery."""
        super().__init__(hass, address, **options)
        self.spacing = max(MIN_SPACING, float(options.get("spacing", 5.0)))
        self.device: dict[str, Any] = {}  # from Sys.GetConfig
        self._lock = asyncio.Lock()
        self._last_start: float | None = None
        self._now: Callable[[], float] = time.monotonic
        self._sleep: Callable[[float], Awaitable[Any]] = asyncio.sleep
        self._acquired = False
        self._last_command: tuple[int, int, int] | None = None

    def url(self, path: str) -> str:
        """Full URL of ``path``, on port 8080 unless the address has one."""
        host = self.address if ":" in self.address else f"{self.address}:8080"
        return f"http://{host}{path}"

    async def _pace(self) -> None:
        """Wait until ``spacing`` has passed since the last request start."""
        if self._last_start is not None:
            wait = self._last_start + self.spacing - self._now()
            if wait > 0:
                await self._sleep(wait)
        self._last_start = self._now()

    async def async_rpc(
        self, method: str, params: dict[str, Any] | None = None, *, get: bool = False
    ) -> Any:
        """Call ``method``; parameters as compact JSON in ``config``. Fresh
        connection, one request at a time, paced."""
        session = async_get_clientsession(self.hass)
        query = (
            {"config": json.dumps(params, separators=(",", ":"))} if params else None
        )
        async with self._lock:
            await self._pace()
            async with (
                asyncio.timeout(self.timeout),
                session.request(
                    "GET" if get else "POST",
                    self.url(f"/rpc/{method}"),
                    params=query,
                    headers={
                        "Connection": "close",
                        "Content-Type": "application/json",
                    },
                ) as response,
            ):
                raw = await response.read()
                response.raise_for_status()
        data = json.loads(raw, parse_constant=_reject)
        if not isinstance(data, dict):
            raise ValueError(f"Indevolt: {method} reply is not an object")
        return data

    async def async_points(self, points: Iterable[int]) -> dict[str, Any]:
        """Read data points (keyed by id as string; missing = unsupported or
        truncated)."""
        ids = list(dict.fromkeys(points))
        if not 1 <= len(ids) <= MAX_POINTS:
            raise ValueError(f"Indevolt: 1-{MAX_POINTS} points per read")
        return await self.async_rpc("Indevolt.GetData", {"t": ids})

    async def async_open(self) -> None:
        """Read the device configuration (only when enabled)."""
        await super().async_open()
        self.device = (await self.async_rpc("Sys.GetConfig", get=True)).get(
            "device"
        ) or {}

    async def async_read(self) -> DirectReading:
        """Read all points in one request and map them."""
        return self.reading(await self.async_points(POINTS.values()))

    def reading(self, data: Any) -> DirectReading:
        """Map a GetData reply onto a reading (+ charging)."""
        data = data if isinstance(data, dict) else {}

        def value(name: str) -> float | None:
            return number(data.get(str(POINTS[name])))

        def mapped(name: str, table: dict[int, str]) -> str | None:
            raw = value(name)
            return None if raw is None else table.get(int(raw))

        def remaining(name: str) -> float | None:
            raw = value(name)
            return None if raw == NOT_APPLICABLE else raw

        battery = value("battery_power")
        ac_total = value("ac_power")
        bypass = value("bypass_power")
        cells = [c for c in (value("cell_a"), value("cell_b")) if c is not None]
        pv_total = value("pv_total")
        code = data.get(str(POINTS["model_code"]))
        model = code_type(code)
        totals = {
            "charged_total_kwh": value("charged_total"),
            "discharged_total_kwh": value("discharged_total"),
            "transformer_temperature_c": value("transformer_temperature"),
        }
        return DirectReading(
            soc=value("soc"),
            power_w=None if battery is None else -battery,
            telemetry=BatteryTelemetry(
                temperature_c=value("battery_temperature"),
                cell_min_v=min(cells) if cells else None,
                cell_max_v=max(cells) if cells else None,
                cycles=value("cycles"),
                charged_today_kwh=value("charged_today"),
                discharged_today_kwh=value("discharged_today"),
                extra={k: v for k, v in totals.items() if v is not None},
            ),
            extra={
                "model_code": code if isinstance(code, str) else None,
                "model": model.type if model else None,
                "ac_power_w": None
                if ac_total is None
                else ac_total - (bypass or 0.0),  # + drawn from AC (charging)
                "bypass_power_w": bypass,
                "pv_power_w": value("pv_power"),
                "pv_total_kwh": None if pv_total is None else pv_total / 1000,
                "grid_power_w": value("grid_power"),  # + import
                "status": mapped("battery_state", BATTERY_STATE),
                "operating_status": mapped("operating_status", OPERATING_STATUS),
                "work_mode": mapped("work_mode", WORK_MODE),
                "device_mode": mapped("device_mode", DEVICE_MODE),
                "realtime_status": mapped("realtime_status", REALTIME_STATUS),
                "realtime_target_soc": value("realtime_target_soc"),
                "realtime_power_w": value("realtime_power"),
                "min_soc": value("reserve_soc"),
                "max_charge_w": lowest(
                    value("max_charge_setting"), value("max_charge_hw")
                ),
                "max_discharge_w": lowest(
                    value("max_discharge_setting"),
                    value("discharge_limit"),
                    value("max_discharge_hw"),
                ),
                "capacity_kwh": value("capacity"),
                "remaining_charge_min": remaining("remaining_charge"),
                "remaining_discharge_min": remaining("remaining_discharge"),
            },
        )

    @staticmethod
    def command(power_w: float, state: dict[str, Any]) -> tuple[int, int, int]:
        """The realtime tuple for a setpoint (+ charge / - discharge), from
        the control points (SoC, reserve, limits); rolling target ±5 %."""
        watts = round(abs(power_w))
        if watts == 0:
            return STOP
        soc = number(state.get("6002"))
        if soc is None:
            raise RuntimeError("Indevolt: state of charge unknown")
        if power_w > 0:
            limit = lowest(number(state.get("11009")), number(state.get("114")))
            target = min(100, math.ceil(soc) + 5)
            action = 1
        else:
            limit = lowest(
                number(state.get("11011")),
                number(state.get("11032")),
                number(state.get("115")),
            )
            floor = max(MIN_TARGET_SOC, number(state.get("6105")) or MIN_TARGET_SOC)
            target = max(math.ceil(floor), math.ceil(soc) - 5)
            action = 2
        if limit is not None:
            watts = min(watts, int(limit))
        return valid_realtime((action, min(watts, MAX_POWER_W), target))

    async def _set_realtime(self, command: tuple[int, int, int]) -> None:
        """The only write this driver can make: point 47015 (RAM)."""
        values = list(valid_realtime(command))
        reply = await self.async_rpc(
            "Indevolt.SetData", {"f": 16, "t": REALTIME_POINT, "v": values}
        )
        if reply.get("result") is not True:
            self._last_command = None  # unknown: may still have applied
            raise RuntimeError(f"Indevolt: realtime command not accepted: {values}")
        self._last_command = command

    async def _stop_and_wait(self) -> None:
        """STOP, then wait for the echo: standby and a quiet battery (it
        trails 9-19 s; up to 30 s, at least two echo reads)."""
        await self._set_realtime(STOP)
        deadline = self._now() + ECHO_TIMEOUT
        reads = 0
        while True:
            echo = await self.async_points(ECHO_POINTS)
            reads += 1
            status = number(echo.get("6107"))
            battery = number(echo.get("6000"))
            ac_total = number(echo.get("2278"))
            ac = None if ac_total is None else ac_total - (number(echo.get("667")) or 0)
            quiet = (battery is not None and abs(battery) <= QUIET_W) or (
                ac is not None and abs(ac) <= QUIET_W
            )
            if status in (0, 1000) and quiet:
                return
            if reads >= 2 and self._now() >= deadline:
                raise RuntimeError("Indevolt: STOP not confirmed by the battery")
            await self._sleep(ECHO_INTERVAL)

    async def async_set_power(self, power_w: float) -> None:
        """Realtime tuple 47015 only: checks the model (known, generation 2)
        and the work mode (realtime, set by the user in the app), STOPs and
        waits for the echo when taking control, then sends the tuple unless
        it equals the last accepted one. NEVER called while HomeBatteryAssist
        is read-only; never writes the work mode or any flash setting.
        Hazards in the module docstring."""
        state = await self.async_points(CONTROL_POINTS)
        model = code_type(state.get("1"))
        if model is None or getattr(model, "api_generation", 0) != 2:
            raise RuntimeError(f"Indevolt: model {state.get('1')!r} not controllable")
        if number(state.get("7101")) != REALTIME_MODE:
            raise RuntimeError("Indevolt: work mode is not realtime (set it in app)")
        if not self._acquired:
            await self._stop_and_wait()
            self._acquired = True
        command = self.command(power_w, state)
        if command != self._last_command:
            await self._set_realtime(command)

    async def async_release(self) -> None:
        """STOP ``[0, 0, 0]`` (accepted); the work mode stays realtime, going
        back to self-consumption is the user's choice in the app. NEVER called
        yet."""
        self._acquired = False
        await self._set_realtime(STOP)


def _reject(constant: str) -> float:
    """Refuse NaN / Infinity in a reply."""
    raise ValueError(f"Indevolt: non-finite number {constant} in reply")
