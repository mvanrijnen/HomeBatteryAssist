"""Direct drivers: Marstek Venus over Modbus TCP (E v3 tested live 2026-11-23; the others not tested).

One driver per hardware version; the battery does not report its own model,
so the user has to pick it:

- ``MarstekVenusEV2Modbus`` — Venus E v2 (32-bit power registers, alarm and
  fault words, SoC cut-off registers);
- ``MarstekVenusEV3Modbus`` — Venus E v3 (SoC at 37005, 16-bit power);
- ``MarstekVenusAModbus`` / ``MarstekVenusDModbus`` — Venus A / D (DC PV
  inputs, several packs; SoC at 32104, 16-bit power).

Reading: function code 3 only, addresses as written (no 40001 offset). Only
directly adjacent registers are read together: a request that spans an
address the firmware does not implement fails as a whole. When a block still
returns a Modbus exception, its points are read one by one from then on.

``power_w`` is the AC-side power (registers 32202 / 30006, + delivering to the
house on the wire), turned into + charging. That is what the house sees and
what is reliable; on the Venus A / D it includes DC PV. The battery-side
power (32102 / 30001, + charging on the wire) is kept as
``battery_power_w``.

Hazards (from the device facts; read them before enabling anything):

- **One TCP client only** (v3, A, D): a second connection locks out the
  current client (e.g. Omnibattery). The battery frees the slot only about
  1 s after a close; reconnecting sooner is refused. Never reconnect after
  each failed request: a reconnect storm can leave the battery unresponsive.
  Note that ``ModbusTcpClient`` reconnects on the next request after an
  error, so a caller must back off itself.
- **Zombie accept** (firmware V150): the socket is accepted, frames are
  ignored. ``async_open`` confirms the connection with one SoC read.
- **Malformed exception frames** (v3 family, TCP): an exception response
  says length 4 where it is 3, so with ``ModbusTcpClient`` it shows as a
  timeout, not as an exception (no block fallback, and a reconnect).
- **Pacing**: at least 150 ms between requests on the v3 family (50 ms on
  v2). Retries should reuse the transaction id (a stalled MCU answers in a
  burst); the Venus D stalls about 4 s every 5 minutes (hence 6 s timeout).
- **Energy counters** can return a partial 32-bit value mid-update; a value
  of 0 or below 90 % of the previous one is dropped. The v3 discharge counter
  does not include backup-port output.
- **Alarm/fault words** (v2, 36000/36100): which register holds bits 0-15 is
  unclear in the source; the raw 32-bit value (first register high) is kept.
- **Multi-pack** (A / D): the aggregate SoC can read 100 % while a pack is
  empty, and 37007/37008 describe pack 1 only. Per-pack SoC sits at
  ``34002 + 100 * (n - 1)`` (0.1 %), per-pack cell max/min at 34005/34006
  with the same stride; ``pack_mask`` (32110) tells which slots are online.

Use: chosen per battery as its direct connection (subentry
``direct_driver``); only then is the driver enabled and does it connect (Omnibattery
or another Modbus client must be switched off first: one client only).
Control (``async_set_power`` / ``async_release``) goes through that
connection: the control test buttons (when switched on) and, once active,
the control loop.

ESPHome variant (LilyGo T-CAN485 bridge on the battery's RS485 port, Venus E
with the v2 map): not a direct driver here. The ESP32 polls the battery about
every 3 s and Home Assistant gets ESPHome entities, matched on the ESPHome
``name`` (e.g. "Battery State Of Charge", "Battery Power", "AC Power",
"Forcible Charge-Discharge", "Forcible Charge Power", "Forcible Discharge
Power", "RS485 Control Mode"). Values are already scaled; control would be
``number.set_value`` / ``select.select_option`` in the same order as below.
Its entities have no translation keys, and its Modbus loop can freeze while
the entities stay available (treat as stalled when no battery entity was
reported for 120 s), so it needs a reader of its own (``integrations/``)
when it is ever supported.

Device facts: Omnibattery (GPL-3.0) ``drivers/marstek.py`` and
``const/registers_*.py``, as facts only; own implementation. Unverified.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, ClassVar

from ...transports.modbus_tcp import ModbusError, decode
from ..base import BatteryCommand
from ..direct.base import DirectBatteryDriver, DirectReading
from ..direct.modbus_driver import ModbusBatteryDriver, Point, blocks
from .venus_a import MarstekVenusA
from .venus_d import MarstekVenusD
from .venus_e_v2 import MarstekVenusEV2
from .venus_e_v3 import MarstekVenusEV3

_LOGGER = logging.getLogger(__name__)

# Control registers (all versions), written with function code 6 only.
RS485_CONTROL = 42000
RS485_ENABLE = 0x55AA  # command values: 0 / 1 give exception 3 on a v3
RS485_DISABLE = 0x55BB
FORCE_MODE = 42010
FORCE_NONE, FORCE_CHARGE, FORCE_DISCHARGE = 0, 1, 2
SET_CHARGE = 42020  # W
SET_DISCHARGE = 42021  # W
BACKUP_FUNCTION = 41200  # 0 = on, 1 = off (inverted)
BACKUP_LOAD_LIMIT_W = 50.0

CONNECT_SETTLE = 0.2  # s after connecting, before the first request
REOPEN_GAP = 1.0  # s between closing and reconnecting (single client slot)
RELEASE_STEP = 0.05  # s between the standby writes on release
RELEASE_SETTLE = 0.1  # s after switching RS485 control off
COUNTER_DROP = 0.9  # a lifetime counter below 90 % of the previous is noise

INVERTER_STATES = {
    0: "sleep",
    1: "standby",
    2: "charging",
    3: "discharging",
    4: "backup",
    5: "ota_upgrade",
    6: "bypass",
}

# Shared by all versions.
COMMON = (
    Point("capacity_kwh", 32105, scale=0.001),  # rated total energy
    Point("temperature_c", 35000, "s16", 0.1),
    Point("inverter_state", 35100),
    Point("cell_max_v", 37007, "s16", 0.001),  # A / D: pack 1 only
    Point("cell_min_v", 37008, "s16", 0.001),
    Point("charged_total_kwh", 33000, "u32", 0.01),
    Point("discharged_total_kwh", 33002, "s32", 0.01),
    Point("backup_function", BACKUP_FUNCTION),
    Point("rs485_control", RS485_CONTROL),
    Point("force_mode", FORCE_MODE),
    Point("charge_setpoint_w", SET_CHARGE),
    Point("discharge_setpoint_w", SET_DISCHARGE),
    Point("max_charge_w", 44002),
    Point("max_discharge_w", 44003),
)

# The v3 family (v3, A, D): 16-bit power registers.
V3_FAMILY = (
    Point("battery_power_w", 30001, "s16"),  # + charging on the wire
    Point("power_w", 30006, "s16", sign=-1.0),  # AC: + delivering on the wire
    Point("off_grid_power_w", 32302, "s16"),
    Point("voltage_v", 30100, scale=0.01),
    Point("cycles", 34003),
)

# Venus A / D: DC PV inputs and multi-pack details.
VENUS_AD = (
    Point("soc", 32104),
    Point("mppt1_w", 30037, scale=0.1),
    Point("mppt2_w", 30038, scale=0.1),
    Point("mppt3_w", 30039, scale=0.1),
    Point("mppt4_w", 30040, scale=0.1),
    Point("pack_mask", 32110),  # bit n = pack slot n + 1 online
    Point("charge_to_soc", 42011),
)


async def _wait(seconds: float) -> None:
    """Pause (separate so tests can skip the waiting)."""
    await asyncio.sleep(seconds)


def _is_exception(err: ModbusError) -> bool:
    """A Modbus exception response (the device refused), not a timeout."""
    return str(err).startswith("exception code")


class MarstekVenusModbus(ModbusBatteryDriver):
    """What the Marstek Venus versions share. Not a driver by itself."""

    can_write = True  # through a direct link only
    enabled = False
    verified = False
    source = (
        "Omnibattery (GPL-3.0) drivers/marstek.py, const/registers_*.py (facts only)"
    )
    port = 502
    unit = 1
    timeout = 3.0
    pause = 0.15  # the TCP server task needs >= 150 ms between requests
    max_block = 125
    ceiling: ClassVar[float] = 2500.0  # W, highest set-point the hardware takes
    # The battery can drop out of forced mode on its own: repeat the command.
    refresh_s = 30.0
    # Each change is three register writes; the battery needs 3-4 s to settle.
    min_interval_s = 5.0
    deadband_w = 25.0

    def __init__(self, hass: Any, address: str, **options: Any) -> None:
        """Initialize; ``options`` may override ``port`` and ``unit``."""
        super().__init__(hass, address, **options)
        self._lock = asyncio.Lock()  # no read between the control writes
        self._single: set[tuple[int, int]] = set()  # blocks read point by point
        self._counters: dict[str, float] = {}
        self._closed_at: float | None = None
        self._control_enabled = False  # RS485 control enabled on this connection
        self.ems_version: int | None = None

    def point(self, name: str) -> Point:
        """The point called ``name``."""
        return next(p for p in self.points if p.name == name)

    def ceiling_w(self) -> float:
        """Highest charge / discharge set-point."""
        return self.ceiling

    async def async_open(self) -> None:
        """Connect (only when enabled) and confirm with one SoC read.

        Waits until the battery has freed its single client slot after a
        previous close, and after connecting before the first request.
        """
        await DirectBatteryDriver.async_open(self)  # refuses when disabled
        self.client.allowed = True
        if self._closed_at is not None:
            remaining = self._closed_at + REOPEN_GAP - time.monotonic()
            if remaining > 0:
                await _wait(remaining)
        await self.client.connect()
        await _wait(CONNECT_SETTLE)
        self._control_enabled = False  # a new connection can reset it
        soc = self.point("soc")
        try:
            await self.client.read_holding(soc.address, 1)
        except ModbusError:
            await self.async_close()
            raise

    async def async_close(self) -> None:
        """Disconnect and remember when (the slot is freed with a delay)."""
        await self.client.close()
        self.client.allowed = False
        self._closed_at = time.monotonic()
        self._control_enabled = False

    async def async_read(self) -> DirectReading:
        """Read all points (adjacent registers together) into a reading."""
        self.require_enabled()
        raw: dict[int, int] = {}
        async with self._lock:
            for _function, start, count in blocks(self.points, self.max_block):
                raw.update(await self._read_block(start, count))
        values: dict[str, float] = {}
        for point in self.points:
            addresses = range(point.address, point.address + point.size)
            if any(a not in raw for a in addresses):
                continue  # not implemented by this firmware
            words = [raw[a] for a in addresses]
            number = decode(words, point.kind, swap_words=point.swap_words)
            values[point.name] = round(number * point.scale * point.sign, 4)
        return self.reading(values)

    async def _read_block(self, start: int, count: int) -> dict[int, int]:
        """Registers ``start``.. as {address: word}; on a Modbus exception
        the block's points are read one by one (also next time)."""
        if (start, count) not in self._single:
            try:
                words = await self.client.read_holding(start, count)
            except ModbusError as err:
                if not _is_exception(err):
                    raise
                inside = [p for p in self.points if start <= p.address < start + count]
                if len(inside) <= 1:
                    return {}
                _LOGGER.debug("%s: block %s+%s refused", self.name, start, count)
                self._single.add((start, count))
            else:
                return {start + i: w for i, w in enumerate(words)}
        result: dict[int, int] = {}
        for point in self.points:
            if not start <= point.address < start + count:
                continue
            try:
                words = await self.client.read_holding(point.address, point.size)
            except ModbusError as err:
                if not _is_exception(err):
                    raise
                continue
            result.update({point.address + i: w for i, w in enumerate(words)})
        return result

    def reading(self, values: dict[str, float]) -> DirectReading:
        """Filter counter noise, derive efficiency / cycles / status."""
        values = dict(values)
        for name in ("charged_total_kwh", "discharged_total_kwh"):
            if (value := values.get(name)) is None:
                continue
            previous = self._counters.get(name)
            if value <= 0 or (previous and value < previous * COUNTER_DROP):
                del values[name]  # partial 32-bit value or a glitch
            else:
                self._counters[name] = value
        charged = values.get("charged_total_kwh")
        discharged = values.get("discharged_total_kwh")
        if charged and discharged is not None:
            values["efficiency_pct"] = round(discharged / charged * 100, 1)
        capacity = values.get("capacity_kwh")
        if "cycles" not in values and capacity and charged and discharged:
            values["cycles"] = round((charged + discharged) / 2 / capacity, 1)
        if (ems := values.get("ems_version")) is not None:
            self.ems_version = int(ems)
        reading = super().reading(values)
        if (state := values.get("inverter_state")) is not None:
            reading.extra["status"] = INVERTER_STATES.get(int(state))
        if mask := int(values.get("pack_mask") or 0):
            reading.extra["packs_online"] = mask.bit_count()
        return reading

    def command(self, reading: DirectReading) -> BatteryCommand | None:
        """The command in the registers: None while RS485 control is off (the
        battery follows its own logic) or unknown."""
        extra = reading.extra
        if extra.get("rs485_control") != RS485_ENABLE:
            return None
        force = extra.get("force_mode")
        if force == FORCE_CHARGE:
            return BatteryCommand(float(extra.get("charge_setpoint_w") or 0.0))
        if force == FORCE_DISCHARGE:
            return BatteryCommand(-float(extra.get("discharge_setpoint_w") or 0.0))
        if force == FORCE_NONE:
            return BatteryCommand(0.0)
        return None

    async def async_set_power(self, power_w: float) -> None:
        """Charge (+) or discharge (-) at ``power_w`` (0 = idle).

        Only through a battery's direct connection (``direct/link.py``),
        chosen per battery; written by the control test or the control loop.

        Sequence: RS485 control on (0x55AA to 42000, once per connection: a
        new connection can reset it), then discharge set-point (42021),
        charge set-point (42020) and force mode (42010), in that order, as
        single-register writes, under a lock so no read gets in between.
        The battery reaches the set-point after about 3-4 s. It can drop
        out of forced mode on its own (BMS full cut-off, short AC loss)
        while acknowledging writes; only a fresh connection (close, wait
        about 1 s, reconnect, enable RS485) recovers that.
        """
        self.require_enabled()
        target = round(power_w)
        ceiling = round(self.ceiling_w())
        if target > 0:
            charge, discharge, force = min(target, ceiling), 0, FORCE_CHARGE
        elif target < 0:
            charge, discharge, force = 0, min(-target, ceiling), FORCE_DISCHARGE
        else:
            charge, discharge, force = 0, 0, FORCE_NONE
        async with self._lock:
            if not self._control_enabled:
                await self.client.write_register(RS485_CONTROL, RS485_ENABLE)
                self._control_enabled = True
            await self.client.write_register(SET_DISCHARGE, discharge)
            await self.client.write_register(SET_CHARGE, charge)
            await self.client.write_register(FORCE_MODE, force)

    async def async_release(self) -> None:
        """Hand control back to the battery's own logic.

        Leaves the battery alone when its backup function is on and the
        backup port carries more than 50 W (or either is unknown). Otherwise:
        standby (discharge 0, charge 0, force mode none, 50 ms apart), RS485
        control off (0x55BB), wait 0.1 s, close (frees the single slot).

        Hazard: switching RS485 control off hands the battery to its own
        logic, and a v3 can then export to the grid by itself. Never write
        "off" as a step before re-enabling control; re-enable with 0x55AA
        directly and write a standby.
        """
        self.require_enabled()
        async with self._lock:
            if not await self._release_allowed():
                _LOGGER.warning(
                    "%s: backup port in use or unknown; not released", self.name
                )
                return
            for register in (SET_DISCHARGE, SET_CHARGE, FORCE_MODE):
                await self.client.write_register(register, 0)
                await _wait(RELEASE_STEP)
            await self.client.write_register(RS485_CONTROL, RS485_DISABLE)
            await _wait(RELEASE_SETTLE)
        await self.async_close()

    async def _release_allowed(self) -> bool:
        """Whether the backup function and backup-port load allow a release."""
        self.require_enabled()
        off_grid = self.point("off_grid_power_w")
        try:
            (backup,) = await self.client.read_holding(BACKUP_FUNCTION, 1)
            if backup != 0:
                return True  # backup function off
            words = await self.client.read_holding(off_grid.address, off_grid.size)
        except ModbusError:
            return False
        load = decode(words, off_grid.kind)
        return abs(load) <= BACKUP_LOAD_LIMIT_W


class MarstekVenusEV2Modbus(MarstekVenusModbus):
    """Marstek Venus E v2 over Modbus TCP (not tested)."""

    key = "marstek_venus_e_v2_modbus"
    name = "Marstek Venus E v2 (Modbus TCP)"
    models = (MarstekVenusEV2,)
    timeout = 10.0
    pause = 0.05
    points = (
        Point("voltage_v", 32100, scale=0.01),
        Point("battery_power_w", 32102, "s32"),  # + charging on the wire
        Point("soc", 32104),
        Point("power_w", 32202, "s32", sign=-1.0),  # AC: + delivering
        Point("off_grid_power_w", 32302, "s32"),
        Point("alarms", 36000, "u32"),
        Point("faults", 36100, "u32"),
        Point("charge_cutoff_pct", 44000, scale=0.1),
        Point("discharge_cutoff_pct", 44001, scale=0.1),
        *COMMON,
    )


class MarstekVenusEV3Modbus(MarstekVenusModbus):
    """Marstek Venus E v3 over Modbus TCP (tested on a device: reading,
    charging, discharging, release, zero on the meter)."""

    verified = True
    key = "marstek_venus_e_v3_modbus"
    name = "Marstek Venus E v3 (Modbus TCP)"
    models = (MarstekVenusEV3,)
    points = (
        Point("soc", 37005),
        Point("balancing", 34009),
        *V3_FAMILY,
        *COMMON,
    )


class MarstekVenusAModbus(MarstekVenusModbus):
    """Marstek Venus A over Modbus TCP (not tested)."""

    key = "marstek_venus_a_modbus"
    name = "Marstek Venus A (Modbus TCP)"
    models = (MarstekVenusA,)
    ceiling = 1500.0
    points = (*VENUS_AD, *V3_FAMILY, *COMMON)


class MarstekVenusDModbus(MarstekVenusModbus):
    """Marstek Venus D over Modbus TCP (not tested).

    The power ceiling depends on the EMS firmware (30200): 2500 W from
    version 149, otherwise (or unknown) 2200 W.
    """

    key = "marstek_venus_d_modbus"
    name = "Marstek Venus D (Modbus TCP)"
    models = (MarstekVenusD,)
    timeout = 6.0  # stalls of about 4 s every 5 minutes
    points = (*VENUS_AD, Point("ems_version", 30200), *V3_FAMILY, *COMMON)

    def ceiling_w(self) -> float:
        """2500 W with EMS firmware 149 or later, else 2200 W."""
        if self.ems_version is not None and self.ems_version >= 149:
            return 2500.0
        return 2200.0
