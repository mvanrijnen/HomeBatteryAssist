"""Direct driver: Anker SOLIX Solarbank over Modbus TCP — PREPARED, NOT USED.

The owner first switches Modbus TCP on in the Anker app (device settings →
"Three-Party Control Settings", which also shows the IP address). Port 502,
unit id 1. Read-only values are input registers (FC04), settings holding
registers (FC03); 32-bit values are big-endian, high word first. Reads stay
inside the vendor's batch ranges (FC04 10000-10050, 10090-10156,
10208-10265, 32768-32774; FC03 10060-10072, 10074-10081, 60000-60003);
0x8007 (32775) is never part of a block read, because firmware without it
answers such a block with a silent zero instead of an error. The device
answers unreliably right after a connect, hence a pause of 0.7 s, and a
pause of 50 ms after every request.

Battery power on the wire is + discharging; it is turned into + charging
here. On the DC-coupled E5000 Pro that register is the pack's power; its AC
contribution is pack power minus the unit's own PV. On the AC models the PV
registers are derived from the device's own AC/P1 calculation, not an
independent PV measurement. The grid register follows the house connection
once an Anker CT meter is attached, not the unit's own AC port.

Control (never called while HomeBatteryAssist is read-only): operating mode
3 (third-party control) in 10064 (FC06), then the set-point in 10071 as a
signed 32-bit value with FC16 (+ discharging on the wire); 10071 is
write-only. Released by set-point 0 and, to hand control back to the app's
own logic, another operating mode (inferred; the facts' sources only write
the 0 W set-point). See ``AnkerModbusDriver.async_set_power`` for the
hazards.

Device facts: Anker's own Home Assistant integration (register map) and
Omnibattery's Anker driver (GPL-3.0), facts only; own implementation.
"""

from __future__ import annotations

import asyncio
import re
from typing import Any, ClassVar, Literal

from ...transports.modbus_tcp import FC_READ_INPUT
from ..direct.base import DirectReading
from ..direct.modbus import ModbusBatteryDriver, Point
from .solarbank_e5000_pro import AnkerSolarbankE5000Pro
from .solarbank_max import AnkerSolarbankMax
from .solarbank_max_ac import AnkerSolarbankMaxAc
from .solarbank_xe import AnkerSolarbankXe
from .solarbank_xe_ac import AnkerSolarbankXeAc

MODELS = (
    AnkerSolarbankMaxAc,
    AnkerSolarbankXeAc,
    AnkerSolarbankE5000Pro,
    AnkerSolarbankMax,
    AnkerSolarbankXe,
)

REG_MODEL = 32768  # FC04, string, 5 registers
REG_SERIAL = 10100  # FC04, string, 12 registers
REG_LIMITS = 10036  # FC04, s32 max charge W, s32 max discharge W
REG_MODE = 10064  # FC03 / FC06, operating mode
REG_SETPOINT = 10071  # FC16, s32 W, + discharging; write-only

MODE_SELF_CONSUMPTION = 0
MODE_THIRD_PARTY = 3
MODES = {
    0: "self_consumption",
    1: "time_of_use",
    3: "third_party",
    4: "custom",
    5: "socket_overlay",
    6: "smart",
    7: "dynamic_pricing",
}
# Operating mode -> bit in the supported-modes mask (32774).
MODE_BITS = {0: 0, 1: 1, 4: 2, 6: 3, 5: 4, 3: 5, 7: 6}
STATUS = {0: "idle", 1: "charging", 2: "discharging", 3: "sleep"}
# Continuous power of the family; the live ceilings can report peak or
# aggregate figures (e.g. 7000 W), and 0 means "not reported".
CONTINUOUS_MAX_W = 3500


Kind = Literal["u16", "s16", "u32", "s32"]


def _input(name: str, address: int, kind: Kind = "u16", **kw: Any) -> Point:
    """An input register point (FC04)."""
    return Point(name, address, kind, function=FC_READ_INPUT, **kw)


def words32(value: int) -> list[int]:
    """A signed 32-bit value as two registers, high word first."""
    value &= 0xFFFFFFFF
    return [value >> 16, value & 0xFFFF]


def ascii_text(registers: list[int]) -> str:
    """Two ASCII bytes per register (high byte first), NULs and spaces
    stripped."""
    raw = b"".join(r.to_bytes(2, "big") for r in registers)
    return raw.decode("ascii", "replace").replace("\x00", "").strip()


def product_code(*texts: str | None) -> str | None:
    """The first known 4-character product code in the model or serial
    register text (letters and digits only, case-insensitive)."""
    codes = {m for model in MODELS for m in model.models if len(m) == 4}
    for text in texts:
        cleaned = re.sub(r"[^A-Z0-9]", "", (text or "").upper())
        for i in range(len(cleaned) - 3):
            if cleaned[i : i + 4] in codes:
                return cleaned[i : i + 4]
    return None


class AnkerModbusDriver(ModbusBatteryDriver):
    """Anker SOLIX Solarbank over Modbus TCP (address = IP / host).

    Option ``dc_coupled`` (the E5000 Pro) adds the unit's own PV power and
    its AC contribution to the reading.
    """

    key = "anker_modbus"
    name = "Anker SOLIX (Modbus TCP)"
    models = MODELS
    can_write = True  # described below; never called
    source = (
        "Anker ha-anker-solix-official register map; Omnibattery "
        "drivers/anker.py (facts only)"
    )
    port = 502
    unit = 1
    timeout = 5.0
    pause = 0.05
    connect_delay: ClassVar[float] = 0.7  # before the first request
    points = (
        _input("status", 10001),
        _input("pcs_pv_power_w", 10002, "s32"),
        _input("third_party_pv_power_w", 10004, "s32"),
        _input("power_w", 10008, "s32", sign=-1),  # + discharging on the wire
        _input("load_power_w", 10010, "s32"),
        _input("grid_power_w", 10012, "s32"),  # + import; house with a CT
        _input("soc", 10014),
        _input("soh_pct", 10015),  # 0 = unknown
        _input("pv_total_kwh", 10018, "u32", scale=0.1),
        _input("max_charge_w", 10036, "s32"),
        _input("max_discharge_w", 10038, "s32"),
        _input("temperature_c", 10156, "s16", scale=0.1),
        _input("ac_output_power_w", 10208, "s32"),
        _input("rated_energy_kwh", 10250, "u32", scale=0.1),
        _input("charged_total_kwh", 10262, "u32", scale=0.1),
        _input("discharged_total_kwh", 10264, "u32", scale=0.1),
        _input("mode_mask", 32774),
        Point("mode", REG_MODE),
        Point("charge_limit_soc", 60000),
        Point("discharge_limit_soc", 60001),
        Point("backup_reserve_soc", 60002),
        Point("backup_soc_enabled", 60003),
    )

    async def async_open(self) -> None:
        """Connect (only when enabled) and give the device a moment."""
        await super().async_open()
        await asyncio.sleep(self.connect_delay)

    async def _async_connected(self) -> None:
        """Reconnect after a lost connection, with the same pause."""
        if not self.client.connected:
            await self.client.connect()
            await asyncio.sleep(self.connect_delay)

    async def async_read(self) -> DirectReading:
        """Read all points (reconnecting with a pause when needed)."""
        await self._async_connected()
        return await super().async_read()

    async def async_identify(self) -> str | None:
        """The product code from the model register, else the serial."""
        await self._async_connected()
        model = ascii_text(await self.client.read_input(REG_MODEL, 5))
        if code := product_code(model):
            return code
        return product_code(ascii_text(await self.client.read_input(REG_SERIAL, 12)))

    def reading(self, values: dict[str, float]) -> DirectReading:
        """Map the values; drop "unknown" zeros and impossible percentages."""
        for key in ("soh_pct", "max_charge_w", "max_discharge_w"):
            if values.get(key) == 0:
                del values[key]
        if (soc := values.get("soc")) is not None and not 0 <= soc <= 100:
            del values["soc"]
        reading = super().reading(values)
        extra = reading.extra
        status = extra.pop("status", None)
        extra["status"] = STATUS.get(int(status)) if status is not None else None
        mode = extra.get("mode")
        extra["mode_name"] = MODES.get(int(mode)) if mode is not None else None
        mask = extra.get("mode_mask")
        if mask is not None:
            extra["supported_modes"] = [
                MODES[m] for m, bit in MODE_BITS.items() if int(mask) >> bit & 1
            ]
        if self.options.get("dc_coupled"):
            pv = max(
                0.0,
                (extra.get("pcs_pv_power_w") or 0.0)
                + (extra.get("third_party_pv_power_w") or 0.0),
            )
            extra["pv_power_w"] = pv
            if reading.power_w is not None:
                # + charging from the AC side: pack power minus own PV
                extra["ac_power_w"] = round(reading.power_w - pv, 4)
        return reading

    def _require_enabled(self) -> None:
        if not self.enabled:
            raise RuntimeError(f"{self.name}: direct driver is not enabled")

    async def _async_limit(self, charge: bool) -> float:
        """The live charge / discharge ceiling, within the continuous power."""
        raw = await self.client.read_input(REG_LIMITS, 4)
        words = raw[0:2] if charge else raw[2:4]
        value = (words[0] << 16) | words[1]
        if value >= 0x80000000:
            value -= 0x100000000
        return float(min(value, CONTINUOUS_MAX_W)) if value > 0 else CONTINUOUS_MAX_W

    async def async_set_power(self, power_w: float) -> None:
        """Charge (+) / discharge (-) at ``power_w``. NEVER called while
        HomeBatteryAssist is read-only.

        Sequence: read the live ceiling (10036 / 10038) and clamp to it and
        to the continuous 3500 W; read the operating mode (10064) and write
        3 (third-party control, FC06) when it is not 3; then write the
        set-point to 10071 as a signed 32-bit value with FC16 (+ discharging
        on the wire). A successful write is the only acknowledgement: 10071
        cannot be read back; check delivery through the battery power.

        Hazards: the device's own Backup Reserve, SoC calibration, "Fast
        Charging" and "Storm Guard" override third-party commands (they can
        drop a discharge and charge at full power); grid feed-in cannot be
        switched on over Modbus, so without it a discharge cannot export;
        the Anker app and Modbus must not fight over the mode; after a
        reconnect the last command must be assumed gone; below about 100 W
        the actual power varies by about ±10 W.
        """
        self._require_enabled()
        await self._async_connected()
        limit = await self._async_limit(power_w >= 0)
        magnitude = min(abs(power_w), limit)
        setpoint = -round(magnitude if power_w >= 0 else -magnitude)
        mode = (await self.client.read_holding(REG_MODE, 1))[0]
        if mode != MODE_THIRD_PARTY:
            await self.client.write_register(REG_MODE, MODE_THIRD_PARTY)
        await self.client.write_registers(REG_SETPOINT, words32(setpoint))

    async def async_release(self) -> None:
        """Set-point 0 (FC16), then the operating mode to return to (option
        ``release_mode``, default 0 = self-consumption, FC06) so the battery
        follows the app's own logic again. NEVER called yet."""
        self._require_enabled()
        await self._async_connected()
        await self.client.write_registers(REG_SETPOINT, words32(0))
        mode = int(self.options.get("release_mode", MODE_SELF_CONSUMPTION))
        await self.client.write_register(REG_MODE, mode)
