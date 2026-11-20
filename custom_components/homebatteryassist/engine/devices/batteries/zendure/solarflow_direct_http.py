"""Direct driver: Zendure SolarFlow over its local HTTP API — PREPARED, NOT
USED.

Reading is one ``GET /properties/report`` (no authentication): a JSON
snapshot with ``sn``, ``product``, ``properties`` and ``packData``. Battery
power is ``outputPackPower`` (into the battery) minus ``packInputPower`` (out
of it), so + charging already. Temperatures are in 0.1 K (°C = (raw -
2731) / 10), voltages in 0.01 V (``BatVolt`` signed 16-bit), ``socSet`` /
``minSoc`` in 0.1 %; ``remainOutTime`` 59940 means "not applicable". The
local API is off by default on newer firmware (add HEMS in the Zendure app,
then exit HEMS).

Control (never called while HomeBatteryAssist is read-only) is a single
``POST /properties/write`` with the serial and only the changed properties:
charge ``acMode`` 1 + ``inputLimit``, discharge / hold ``acMode`` 2 +
``outputLimit``, always with ``smartMode`` 1 (RAM only). Hazards:

- ``smartMode`` is sticky: a write without it inherits the last value, and
  ``smartMode`` 0 writes flash; in a power loop that wears the flash out;
- with HEMS on in the app the device overrides a setpoint within 10-14 s;
- during SoC calibration (``socStatus`` 1) the device ignores setpoints;
- the report echoes the previous limits for about 2 s after a write;
- ``socSet`` / ``minSoc`` are 0.1 % on the wire (writing 100 sets 10 %);
- writing would compete with another integration that controls the battery.

Device facts: Zendure's zenSDK documentation, the Zendure-HA integration and
Omnibattery's Zendure driver (GPL-3.0) as reference for facts only; own
implementation.
"""

from __future__ import annotations

import asyncio
import math
import re
from typing import Any

import aiohttp
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from ..base import BatteryModel, BatteryTelemetry
from ..direct.base import DirectReading
from ..direct.http_driver import HttpBatteryDriver
from .solarflow_800 import ZendureSolarFlow800
from .solarflow_800_plus import ZendureSolarFlow800Plus
from .solarflow_800_pro import ZendureSolarFlow800Pro
from .solarflow_1600_ac_plus import ZendureSolarFlow1600AcPlus
from .solarflow_2400_ac_plus import ZendureSolarFlow2400AcPlus
from .solarflow_2400_pro import ZendureSolarFlow2400Pro

KELVIN_OFFSET = 2731  # 0.1 K
NOT_APPLICABLE_MINUTES = 59940  # remainOutTime: 999 h = idle
PACK_STATE = {0: "idle", 1: "charging", 2: "discharging"}
AC_CHARGE = 1  # acMode: input
AC_DISCHARGE = 2  # acMode: output
RETRY_DELAY = 0.5  # s, once on HTTP 431 or a dropped connection

# Normalised ``product`` (lower case, [a-z0-9] only) → type, checked in this
# order. The Mix models (3000/4000) are recognised so they do not fall
# through to "pro" / "any other", but have no type here yet.
Match = tuple[tuple[str, ...], tuple[str, ...], type[BatteryModel] | None]
PRODUCTS: tuple[Match, ...] = (
    (("4000mixpro",), ("zda2501",), None),
    (("4000mixac",), ("zda2502",), None),
    (("3000mixac",), (), None),
    (("800pro",), (), ZendureSolarFlow800Pro),
    (("800plus", "800pls"), (), ZendureSolarFlow800Plus),
    (("solarflow800",), ("zdsf800",), ZendureSolarFlow800),
    (("1600ac",), ("zdsf1600",), ZendureSolarFlow1600AcPlus),
    (("pro",), (), ZendureSolarFlow2400Pro),
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


def celsius(value: Any) -> float | None:
    """0.1 K on the wire → °C."""
    raw = number(value)
    return None if raw is None else round((raw - KELVIN_OFFSET) / 10, 1)


def int16(raw: float) -> float:
    """Two's complement of a 16-bit value."""
    return raw - 65536 if raw >= 32768 else raw


def product_type(product: Any) -> type[BatteryModel] | None:
    """The type of a report's ``product`` string (None = Mix / unknown)."""
    name = re.sub(r"[^a-z0-9]", "", str(product or "").lower())
    if not name:
        return ZendureSolarFlow2400Pro  # as Omnibattery's fallback
    for contains, starts, model in PRODUCTS:
        if any(c in name for c in contains) or any(name.startswith(s) for s in starts):
            return model
    return ZendureSolarFlow2400AcPlus


def pack_capacity_kwh(pack: dict[str, Any]) -> float | None:
    """Capacity of one pack from its serial (first character = family)."""
    serial = str(pack.get("sn") or "")
    if not serial:
        return None
    family = serial[0].upper()
    if family == "A":
        return 2.4 if serial[3:4] == "3" else 0.96
    if family == "B":
        return 8.0 if number(pack.get("packType")) == 70 else 0.96
    return {"C": 1.92, "F": 2.88, "G": 2.88, "J": 2.4}.get(family)


def total_capacity_kwh(
    packs: list[dict[str, Any]], count: float | None
) -> float | None:
    """Total capacity, only when every pack is identified, their number is
    ``packNum`` and the serials are unique."""
    sizes = [pack_capacity_kwh(p) for p in packs]
    serials = {p.get("sn") for p in packs}
    if not packs or None in sizes or count != len(packs) or len(serials) != len(packs):
        return None
    return round(sum(s for s in sizes if s is not None), 2)


class ZendureHttpDriver(HttpBatteryDriver):
    """Zendure SolarFlow over the local HTTP API (address = host[:port])."""

    key = "zendure_http"
    name = "Zendure SolarFlow (HTTP)"
    models = (
        ZendureSolarFlow800,
        ZendureSolarFlow800Plus,
        ZendureSolarFlow800Pro,
        ZendureSolarFlow1600AcPlus,
        ZendureSolarFlow2400AcPlus,
        ZendureSolarFlow2400Pro,
    )
    can_write = True  # described below; never called
    source = "Zendure zenSDK docs, Zendure-HA, Omnibattery zendure.py (facts only)"
    status_path = "/properties/report"
    write_path = "/properties/write"
    timeout = 10.0

    def __init__(self, hass: Any, address: str, **options: Any) -> None:
        """Initialize; the serial is learnt from the first report."""
        super().__init__(hass, address, **options)
        self.serial: str | None = None

    async def _request(self, method: str, path: str, body: Any = None) -> Any:
        """One request as JSON, retried once after 0.5 s on HTTP 431 or a
        dropped connection (the small server drops idle keep-alives; writes
        set absolute values, so a retry is safe)."""
        self.require_enabled()
        session = async_get_clientsession(self.hass)
        for attempt in range(2):
            try:
                async with (
                    asyncio.timeout(self.timeout),
                    session.request(
                        method, self.url(path), json=body, auth=self.auth()
                    ) as response,
                ):
                    retry = response.status == 431 and attempt == 0
                    if not retry:
                        response.raise_for_status()
                        return await response.json(content_type=None)
                await asyncio.sleep(RETRY_DELAY)  # the response is released
                continue
            except (aiohttp.ClientConnectionError, OSError):
                if attempt:
                    raise
                await asyncio.sleep(RETRY_DELAY)
        return None

    async def async_get(self, path: str) -> Any:
        """GET ``path`` as JSON (with the retry above)."""
        return await self._request("GET", path)

    def reading(self, data: Any) -> DirectReading:
        """Map a report onto a reading (+ charging)."""
        data = data if isinstance(data, dict) else {}
        props: dict[str, Any] = data.get("properties") or {}
        packs = [p for p in data.get("packData") or [] if isinstance(p, dict)]
        if data.get("sn"):
            self.serial = str(data["sn"])

        into = number(props.get("outputPackPower"))
        out = number(props.get("packInputPower"))
        power = None if into is None or out is None else into - out
        grid_in = number(props.get("gridInputPower"))
        home_out = number(props.get("outputHomePower"))
        ac_power = (
            grid_in - home_out
            if grid_in is not None
            and home_out is not None
            and grid_in >= 0
            and home_out >= 0
            else None
        )
        volt = number(props.get("BatVolt"))
        remaining = number(props.get("remainOutTime"))
        if remaining == NOT_APPLICABLE_MINUTES:
            remaining = None
        soc_set = number(props.get("socSet"))
        min_soc = number(props.get("minSoc"))
        cell_min = [v for p in packs if (v := number(p.get("minVol"))) is not None]
        cell_max = [v for p in packs if (v := number(p.get("maxVol"))) is not None]
        pack_temps = [t for p in packs if (t := celsius(p.get("maxTemp"))) is not None]
        state = number(props.get("packState"))
        model = product_type(data.get("product"))
        pack_count = number(props.get("packNum"))
        return DirectReading(
            soc=number(props.get("electricLevel")),
            power_w=power,
            telemetry=BatteryTelemetry(
                temperature_c=max(pack_temps) if pack_temps else None,
                voltage_v=None if volt is None else round(int16(volt) / 100, 2),
                cell_min_v=min(cell_min) / 100 if cell_min else None,
                cell_max_v=max(cell_max) / 100 if cell_max else None,
                extra={
                    k: v
                    for k, v in {
                        "enclosure_temperature_c": celsius(props.get("hyperTmp")),
                    }.items()
                    if v is not None
                },
            ),
            extra={
                "sn": self.serial,
                "product": data.get("product"),
                "model": model.type if model else None,
                "ac_power_w": ac_power,  # + drawn from AC (charging)
                "pv_power_w": number(props.get("solarInputPower")),
                "off_grid_power_w": number(props.get("gridOffPower")),
                "status": PACK_STATE.get(int(state)) if state is not None else None,
                "soc_calibration": number(props.get("socStatus")) == 1,
                "soc_limit_state": number(props.get("socLimit")),
                "remaining_discharge_min": remaining,
                "max_charge_w": number(props.get("chargeMaxLimit")),
                "max_discharge_w": number(props.get("inverseMaxPower")),
                "ac_mode": number(props.get("acMode")),
                "input_limit_w": number(props.get("inputLimit")),
                "output_limit_w": number(props.get("outputLimit")),
                "max_soc": None if soc_set is None else soc_set / 10,
                "min_soc": None if min_soc is None else min_soc / 10,
                "packs": pack_count,
                "capacity_kwh": total_capacity_kwh(packs, pack_count),
                "fault_level": number(props.get("faultLevel")),
                "error": number(props.get("is_error")) == 1,
            },
        )

    def power_properties(self, power_w: float) -> dict[str, int]:
        """The write for a setpoint (+ charge / - discharge), smartMode 1."""
        watts = round(abs(power_w))
        if power_w > 0:
            return {"acMode": AC_CHARGE, "inputLimit": watts, "smartMode": 1}
        return {"acMode": AC_DISCHARGE, "outputLimit": watts, "smartMode": 1}

    async def async_write(self, properties: dict[str, int]) -> None:
        """POST the changed properties with the serial (read first if not
        known). Refuses a write without ``smartMode`` 1 (flash wear)."""
        if properties.get("smartMode") != 1:
            raise ValueError("Zendure: every write must set smartMode 1")
        if self.serial is None:
            self.reading(await self.async_get(self.status_path))
        if not self.serial:
            raise RuntimeError("Zendure: serial number unknown")
        await self._request(
            "POST", self.write_path, {"sn": self.serial, "properties": properties}
        )

    async def async_set_power(self, power_w: float) -> None:
        """Charge (``acMode`` 1 + ``inputLimit``) or discharge / hold
        (``acMode`` 2 + ``outputLimit``) in one write, always ``smartMode`` 1.
        NEVER called while HomeBatteryAssist is read-only; hazards in the
        module docstring (HEMS must be off, calibration, sticky smartMode)."""
        await self.async_write(self.power_properties(power_w))

    async def async_release(self) -> None:
        """Hold at 0 W (``acMode`` 2, ``outputLimit`` 0, ``smartMode`` 1);
        not persisted, so a reboot or re-enabling HEMS in the app restores the
        battery's own control. NEVER called yet."""
        await self.async_write(self.power_properties(0.0))
