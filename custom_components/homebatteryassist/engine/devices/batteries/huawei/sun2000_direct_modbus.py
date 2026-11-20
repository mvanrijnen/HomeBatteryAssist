"""Direct driver: Huawei LUNA2000 through its SUN2000 hybrid inverter over
Modbus TCP — PREPARED, NOT USED.

The battery is read at the inverter's unit id (factory default 1 for a
direct connection; dongles and EMMAs often use another one, and a wrong id
can return another device's data). Port 502, holding registers only (FC03;
input registers get no answer), writes with FC16 only, 32-bit values high
word first. The inverter drops a request that arrives too soon after the
TCP handshake (pause 1.5 s after connecting), handles exactly one request at
a time, and accepts ONE Modbus client: anything else on it (``huawei_solar``,
evcc, ...) takes that connection unless a Modbus proxy sits in front.

"Not available" comes back as a successful read: u16 0xFFFF, s16 0x7FFF,
u32 0xFFFFFFFF, s32 0x7FFFFFFF. Such values are dropped (never scaled into a
number), as are percentages outside 0-100 and powers beyond ±1 MW. Battery
power on the wire is already + charging. The inverter's AC power includes
PV, so it is not the battery's AC contribution.

Control (never called while HomeBatteryAssist is read-only) is Huawei's
forcible charge / discharge: power, duration, target "by time", then the
mode register last; released with the mode register first. See
``HuaweiModbusDriver.async_set_power`` for the hazards.

Device facts: Omnibattery's Huawei driver and research notes (GPL-3.0),
built on the ``huawei_solar`` register map and Huawei's Modbus interface
definitions; facts only, own implementation. Verified there on one
installation (SUN2000-8K-MAP0 with two LUNA2000-7-E1 packs).
"""

from __future__ import annotations

import asyncio
from typing import ClassVar

from ..direct.base import DirectReading
from ..direct.modbus_driver import ModbusBatteryDriver, Point
from .luna2000_e1 import HuaweiLuna2000E1

REG_INVERTER_MODEL = 30000  # string, 15 registers ("SUN2000...")
REG_LIMITS = 37046  # u32 max charge W, u32 max discharge W
REG_PERIOD = 47083  # forcible duration, minutes
REG_FORCIBLE = 47100  # 0 stop, 1 charge, 2 discharge
REG_TARGET = 47246  # 0 = by time
REG_CHARGE_W = 47247  # u32
REG_DISCHARGE_W = 47249  # u32

FORCIBLE_STOP, FORCIBLE_CHARGE, FORCIBLE_DISCHARGE = 0, 1, 2
TARGET_BY_TIME = 0
DEFAULT_DURATION_MIN = 10
SENTINELS = {"u16": 0xFFFF, "s16": 0x7FFF, "u32": 0xFFFFFFFF, "s32": 0x7FFFFFFF}
MAX_POWER_W = 1_000_000  # beyond this a value is a decode fault
PERCENTAGES = ("soc", "charge_cutoff_soc", "discharge_cutoff_soc")
DIRECTION_DEADBAND_W = 100  # the inverter idles at about +50 W
STATUS = {0: "offline", 1: "idle", 2: "running", 3: "fault", 4: "sleep"}
WORKING_MODES = {
    0: "adaptive",
    1: "fixed_charge_discharge",
    2: "max_self_consumption",
    3: "time_of_use_lg",
    4: "fully_fed_to_grid",
    5: "time_of_use_luna2000",
}
STORAGE_TYPES = {0: "none", 1: "lg_resu", 2: "luna2000"}


def words32(value: int) -> list[int]:
    """An unsigned 32-bit value as two registers, high word first."""
    value &= 0xFFFFFFFF
    return [value >> 16, value & 0xFFFF]


def ascii_text(registers: list[int]) -> str:
    """Two ASCII bytes per register (high byte first), NUL padding removed."""
    raw = b"".join(r.to_bytes(2, "big") for r in registers)
    return raw.split(b"\x00", 1)[0].decode("ascii", "replace").strip()


def is_power(name: str) -> bool:
    """Whether a point is a power in W."""
    return name == "power_w" or name.endswith("_w")


class HuaweiModbusDriver(ModbusBatteryDriver):
    """Huawei LUNA2000 through a SUN2000 inverter (address = IP / host;
    option ``unit`` = the inverter's unit id)."""

    key = "huawei_modbus"
    name = "Huawei SUN2000 + LUNA2000 (Modbus TCP)"
    models = (HuaweiLuna2000E1,)
    can_write = True  # described below; never called
    # Control needs (engine/control): slow ramp and write throttle; 0 W is not
    # idle (it derates PV), so idle is a release; refresh the command.
    min_interval_s = 20.0
    deadband_w = 250.0
    refresh_s = 240.0
    idle_is_release = True
    source = "Omnibattery drivers/huawei.py and Huawei research notes (facts only)"
    port = 502
    unit = 1
    timeout = 10.0
    pause = 0.05  # between requests; one request in flight
    connect_delay: ClassVar[float] = 1.5  # the inverter drops earlier requests
    points = (
        # Battery
        Point("status", 37000),
        Point("power_w", 37001, "s32"),  # + charging
        Point("voltage_v", 37003, scale=0.1),
        Point("soc", 37004, scale=0.1),
        Point("charged_today_kwh", 37015, "u32", scale=0.01),
        Point("discharged_today_kwh", 37017, "u32", scale=0.01),
        Point("temperature_c", 37022, "s16", scale=0.1),
        Point("max_charge_w", 37046, "u32"),  # live; depends on the packs
        Point("max_discharge_w", 37048, "u32"),
        Point("charged_total_kwh", 37066, "u32", scale=0.01),
        Point("discharged_total_kwh", 37068, "u32", scale=0.01),
        Point("capacity_kwh", 37758, "u32", scale=0.001),  # Wh on the wire
        # Inverter / PV
        Point("rated_power_w", 30073, "u32"),
        Point("max_active_power_w", 30075, "u32"),  # enforced AC ceiling
        Point("state3", 32003, "u32"),  # bit0 off-grid now
        Point("pv_power_w", 32064, "s32"),
        Point("inverter_power_w", 32080, "s32"),  # whole inverter, PV included
        # Settings
        Point("storage_type", 47000),
        Point("charge_cutoff_soc", 47081, scale=0.1),
        Point("discharge_cutoff_soc", 47082, scale=0.1),
        Point("forcible_period_min", REG_PERIOD),
        Point("working_mode", 47086),
        Point("charge_from_grid", 47087),
        Point("forcible_mode", REG_FORCIBLE),
        Point("forcible_target", REG_TARGET),
        Point("forcible_charge_w", REG_CHARGE_W, "u32"),
        Point("forcible_discharge_w", REG_DISCHARGE_W, "u32"),
    )

    async def async_open(self) -> None:
        """Connect (only when enabled) and wait before the first request."""
        await super().async_open()
        await asyncio.sleep(self.connect_delay)

    async def _async_connected(self) -> None:
        """Reconnect after a lost connection, with the same pause."""
        self.require_enabled()
        if not self.client.connected:
            await self.client.connect()
            await asyncio.sleep(self.connect_delay)

    async def async_read(self) -> DirectReading:
        """Read all points (reconnecting with a pause when needed)."""
        await self._async_connected()
        return await super().async_read()

    async def async_identify(self) -> str | None:
        """The inverter's model name (e.g. ``SUN2000-8K-MAP0``); None when
        the unit id answers as something else (e.g. an EMMA, ``SmartHEMS``).
        A battery is present only when the state of charge reads valid."""
        self.require_enabled()
        await self._async_connected()
        model = ascii_text(await self.client.read_holding(REG_INVERTER_MODEL, 15))
        return model if model.startswith("SUN2000") else None

    def valid(self, values: dict[str, float]) -> dict[str, float]:
        """Without "not available" markers and implausible values.

        The markers are recognised exactly: the base driver scales a raw
        value the same way for every read, so a scaled marker is a fixed
        number per point (scaling is one-to-one)."""
        result: dict[str, float] = {}
        for point in self.points:
            if (value := values.get(point.name)) is None:
                continue
            marker = SENTINELS[point.kind] * point.scale * point.sign
            if value == round(marker, 4):
                continue
            if point.name in PERCENTAGES and not 0 <= value <= 100:
                continue
            if is_power(point.name) and abs(value) > MAX_POWER_W:
                continue
            result[point.name] = value
        return result

    def reading(self, values: dict[str, float]) -> DirectReading:
        """Map the valid values; status refined by the power's direction."""
        reading = super().reading(self.valid(values))
        extra = reading.extra
        power = reading.power_w
        raw = extra.pop("status", None)
        status = STATUS.get(int(raw)) if raw is not None else None
        if status == "running" and power is not None:
            if power > DIRECTION_DEADBAND_W:
                status = "charging"
            elif power < -DIRECTION_DEADBAND_W:
                status = "discharging"
            else:
                status = "idle"
        extra["status"] = status
        if (mode := extra.get("working_mode")) is not None:
            extra["working_mode_name"] = WORKING_MODES.get(int(mode))
        if (storage := extra.get("storage_type")) is not None:
            extra["storage_type_name"] = STORAGE_TYPES.get(int(storage))
        inverter = extra.get("inverter_power_w")
        if (state3 := extra.pop("state3", None)) is not None:
            off_grid = bool(int(state3) & 1)
            extra["off_grid"] = off_grid
            if inverter is not None:
                extra["off_grid_power_w"] = max(0.0, inverter) if off_grid else 0.0
        forcible = extra.get("forcible_mode")
        if forcible == FORCIBLE_CHARGE:
            extra["forcible_setpoint_w"] = extra.get("forcible_charge_w")
        elif forcible == FORCIBLE_DISCHARGE:
            discharge = extra.get("forcible_discharge_w")
            extra["forcible_setpoint_w"] = None if discharge is None else -discharge
        elif forcible is not None:
            extra["forcible_setpoint_w"] = 0.0
        ceiling = extra.get("max_active_power_w")
        if ceiling is not None and inverter is not None and power is not None:
            # AC headroom left for discharging, without the battery's own share
            others = max(0.0, inverter - max(0.0, -power))
            extra["discharge_headroom_w"] = ceiling - others
        return reading

    def _require_enabled(self) -> None:
        if not self.enabled:
            raise RuntimeError(f"{self.name}: direct driver is not enabled")

    async def async_set_power(
        self, power_w: float, duration_min: int = DEFAULT_DURATION_MIN
    ) -> None:
        """Forcible charge (+) / discharge (-) at ``power_w`` for
        ``duration_min`` minutes (1-1440). NEVER called while
        HomeBatteryAssist is read-only.

        Sequence (FC16, mode register LAST, so a sequence that fails part-way
        leaves the inverter doing what it did): the live limit (37046 /
        37048) is read and the power clamped to it (a higher value is
        refused, not trimmed); 47247 (charge) or 47249 (discharge) ← power
        (u32); 47083 ← duration; 47246 ← 0 (by time); 47100 ← 1 (charge) or
        2 (discharge). 0 W is a release, never a forcible 0 W charge.

        Hazards:

        - a forcible command limits PV production: the inverter delivers
          exactly the commanded power and curtails the array to match; a
          forcible discharge stops the MPPT completely (strings at
          open-circuit voltage), and the missing PV then looks like a
          deficit asking for even more discharge. In daylight only a charge
          above the current harvest does not bind;
        - a held forcible charge at 0 W makes the inverter derate PV: idle
          must be the release;
        - the duration is NO watchdog: a command was seen still active hours
          after its duration ended. Always release explicitly, over the same
          path that commanded;
        - frequent commands make the inverter derate PV: a controller must
          leave at least 20 s between writes, skip changes under 250 W and
          refresh a standing command after about 240 s;
        - the battery ramps slowly (about 20 s to 90 %); the command
          registers echo at once, the battery power does not;
        - the inverter's own energy manager (EMMA) regulates the same grid
          meter when released;
        - the inverter accepts ONE Modbus client: this would take the
          connection of any other integration on it.
        """
        self._require_enabled()
        if not 1 <= duration_min <= 1440:
            raise ValueError(f"duration {duration_min} min out of range 1-1440")
        if round(power_w) == 0:
            await self.async_release()
            return
        await self._async_connected()
        charge = power_w > 0
        limits = await self.client.read_holding(REG_LIMITS, 4)
        words = limits[0:2] if charge else limits[2:4]
        limit = (words[0] << 16) | words[1]
        if limit == SENTINELS["u32"]:
            raise RuntimeError(f"{self.name}: power limit not available")
        power = min(round(abs(power_w)), limit)
        await self.client.write_registers(
            REG_CHARGE_W if charge else REG_DISCHARGE_W, words32(power)
        )
        await self.client.write_registers(REG_PERIOD, [duration_min])
        await self.client.write_registers(REG_TARGET, [TARGET_BY_TIME])
        await self.client.write_registers(
            REG_FORCIBLE, [FORCIBLE_CHARGE if charge else FORCIBLE_DISCHARGE]
        )

    async def async_release(self) -> None:
        """Stop the forcible command and hand the battery back to its working
        mode (47086, e.g. self-consumption). NEVER called yet.

        Sequence (FC16, mode register FIRST): 47100 ← 0 (stop); 47249 ← 0
        (u32); 47083 ← 0; 47246 ← 0."""
        self._require_enabled()
        await self._async_connected()
        await self.client.write_registers(REG_FORCIBLE, [FORCIBLE_STOP])
        await self.client.write_registers(REG_DISCHARGE_W, words32(0))
        await self.client.write_registers(REG_PERIOD, [0])
        await self.client.write_registers(REG_TARGET, [TARGET_BY_TIME])
