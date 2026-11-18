"""Any SunSpec inverter via Modbus TCP (the vendor-neutral register map).

SunSpec is a standard Modbus register map that many inverters offer next to
their own (SMA, Fronius, SolarEdge, Kostal, Huawei, ABB / FIMER, ...). The map
starts at 40000 with the marker ``SunS`` (0x53756E53); after it come models,
each ``ID`` + length ``L`` + its points, until ID 0xFFFF. The addresses of a
model therefore differ per device: a driver walks the chain to find them.

For limiting the power the driver uses model **123** (Immediate Controls):

- ``WMaxLimPct`` (offset 3): the power limit in % of ``WMax`` (model 121,
  Basic Settings; else ``WRtg`` of model 120, Nameplate), scaled by
  ``WMaxLimPct_SF`` (offset 21): written value = % / 10^SF;
- ``WMaxLimPct_RvrtTms`` (offset 5): after this many seconds without a new
  write the inverter falls back to full power by itself (a safety net when
  HomeBatteryAssist would stop);
- ``WMaxLim_Ena`` (offset 7): 1 = the limit is active, 0 = off.

Offsets are counted from the first point after ``ID`` and ``L``. Newer
devices (SunSpec 2018 / IEEE 1547) may offer model 704 instead; not covered
yet. On SMA: Sunny Boy 1AV-41 from firmware 4.00.23.R, Sunny Tripower
3AV-40 from 4.00.02.R and CORE1 from 3.14 offer models 1, 101-103, 120-123;
model 123 may be written cyclically (no flash wear); unit = SMA unit + 123.
The unit id differs per brand (SMA 126, Fronius 1, SolarEdge 1); the
address is ``host[:port][/unit]``. From the SunSpec specification, *not
verified on a device*. Modbus (SunSpec) must be switched on in the inverter;
with an SMA Sunny Home Manager the limit belongs to the Home Manager
(``sma_home_manager.py``). In this phase nothing is sent and no connection is
opened.
"""

from __future__ import annotations

from .base import InverterDriver, Point

# Where the SunSpec map starts and its marker ("SunS").
SUNSPEC_BASE = 40000
SUNSPEC_MARKER = 0x53756E53
# Immediate Controls and the points used (offsets after ID and L).
MODEL_IMMEDIATE_CONTROLS = 123
MODEL_BASIC_SETTINGS = 121  # WMax
MODEL_NAMEPLATE = 120  # WRtg (when model 121 is missing)
REVERT_S = 60  # fall back to full power after 60 s without a write


class SunSpecModbusInverterDriver(InverterDriver):
    """A SunSpec inverter, power limit via model 123 (Immediate Controls)."""

    key = "sunspec_modbus"
    name = "SunSpec Modbus"
    limits = "power"
    # Addresses are offsets inside model 123 (found by walking the chain).
    points = (
        Point(3, "WMaxLimPct (% of WMax)", "{limit_w} W as % of WMax"),
        Point(5, "WMaxLimPct_RvrtTms (s)", str(REVERT_S)),
        Point(7, "WMaxLim_Ena", "1"),
    )

    def describe(self, address: str, limit_w: float) -> str:
        """What it would send, with the model-relative offsets."""
        parts = [
            f"{p.name.split(' ')[0]}={p.value.format(limit_w=round(limit_w))}"
            for p in self.points
        ]
        return f"{self.name} {address}: model {MODEL_IMMEDIATE_CONTROLS} " + ", ".join(
            parts
        )
