"""Older SMA inverters (Sunny Boy TL-21, Sunny Tripower TL-10/-20/-30) via
Modbus TCP, without a Sunny Home Manager.

With a Sunny Home Manager the limit belongs to it (``sma_home_manager.py``).
Newer SMA inverters (Sunny Boy 1AV-40/41, Sunny Tripower 3AV-40, CORE1) are
limited through SunSpec (``sunspec_modbus.py``, unit 126); the Sunny
Tripower Storage X through ``sma_storage_x.py``.

These older types take a normalised active power limit: register **40023**
in % x 100 (100 % = 10000, S16 FIX2, write only; unit 3, port 502), a grid
management value that may be written cyclically. The fallback when the
setpoints stop is set in the inverter's web interface (*Operating mode for
absent plant control* = *Use fallback setting*, *Fallback act power lmt P in
% of WMax*); without it the inverter keeps the last limit. Confirmed by
users on an STP 9000TL-20 and STP 15000TL-10, *not verified here*. Never
write ``WMax`` (40915) cyclically: it is stored in flash (SMA: cyclic changes
destroy the flash memory). Modbus must be switched on. In this phase
nothing is sent.
"""

from __future__ import annotations

from .base import InverterDriver, Point


class SmaModbusInverterDriver(InverterDriver):
    """Older SMA inverter without a Home Manager, % limit via Modbus."""

    key = "sma_modbus"
    name = "SMA Modbus (TL)"
    limits = "power"
    points = (
        Point(
            40023,
            "Active power limit (% x 100 of WMax)",
            "{limit_w} W as % x 100 of WMax",
            3,
        ),
    )
