"""What a battery can do at its temperature: observations to learn from.

A battery's own management (BMS) lowers the charge power when it is cold
(lithium iron phosphate must not charge near 0 °C) and both powers when it is
hot. The specifications rarely say how much, and a battery in a garage or a
shed has its own climate. So per real battery this records, every look of
the command check (``CommandMonitor``, every 15 s):

- **Power per temperature band** (``BAND_C`` wide), apart for charging and
  discharging: how often the battery was asked for a power it could have
  given (asked at least ``MIN_ASK_W``, the same command as the look before so
  ramping does not count, not near full or empty, charging/discharging
  allowed, no hysteresis) and how often it gave clearly less
  (``LIMITED_SHARE``), with what it gave then.
- **Hours**: per hour the battery's mean temperature, the outdoor temperature
  and the energy through the battery — to learn later how the battery's
  temperature follows the outdoor temperature (at rest) and how much it warms
  up while in use.

Only recorded for now (diagnostics); the plans do not use it yet (backlog:
plan per slot with the power that fits the expected battery temperature).
"""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from ...const import DOMAIN
from ..devices.batteries import BatteryCommand
from ..measure.battery_monitor import BatteryConfig
from .command_check import reason_for

STORAGE_VERSION = 1
BAND_C = 2.0  # width of a temperature band (°C)
MIN_ASK_W = 100.0  # smaller commands say nothing about a limit
LIMITED_SHARE = 0.9  # gives less than this share of what it is asked: limited
SAME_COMMAND = 0.05  # the command changed less than this share: the same
NEAR_LIMIT = 5.0  # % from the minimum / maximum: the BMS tapers there anyway
MAX_GAP = timedelta(seconds=60)  # a longer gap between looks counts as this
KEEP = timedelta(days=60)  # hours kept
SAVE_DELAY = 600  # seconds


def band_of(celsius: float) -> int:
    """The temperature band (its lower bound, °C) holding ``celsius``."""
    return int(math.floor(celsius / BAND_C) * BAND_C)


@dataclass
class _Hour:
    start: datetime
    temp_cs: float = 0.0  # °C x seconds
    temp_s: float = 0.0
    outdoor_cs: float = 0.0
    outdoor_s: float = 0.0
    wh: float = 0.0  # energy through the battery (charged + discharged)


@dataclass
class BatteryTemperature:
    """The observations of one battery."""

    # direction ("charge" / "discharge") -> band (str °C) ->
    # {"n", "limited", "given_w" (sum while limited), "max_w" (most given)}
    bands: dict[str, dict[str, dict[str, float]]] = field(
        default_factory=lambda: {"charge": {}, "discharge": {}}
    )
    # {"start", "temp_c", "outdoor_c", "kwh"} per finished hour
    hours: list[dict[str, Any]] = field(default_factory=list)
    _hour: _Hour | None = None
    _last: datetime | None = None
    _last_command: float | None = None

    def observe(
        self,
        when: datetime,
        config: BatteryConfig,
        command: BatteryCommand | None,
        soc: float | None,
        power_w: float | None,
        temperature_c: float | None,
        outdoor_c: float | None = None,
    ) -> None:
        """One look at the battery."""
        seconds = 0.0
        if self._last is not None and when > self._last:
            seconds = min(when - self._last, MAX_GAP).total_seconds()
        self._last = when
        self._add_hour(when, seconds, power_w, temperature_c, outdoor_c)
        asked_w = command.power_w if command is not None else None
        same = (
            asked_w is not None
            and self._last_command is not None
            and abs(asked_w - self._last_command)
            <= SAME_COMMAND * max(abs(asked_w), abs(self._last_command))
        )
        self._last_command = asked_w
        if (
            command is None
            or asked_w is None
            or not same
            or power_w is None
            or temperature_c is None
            or abs(asked_w) < MIN_ASK_W
        ):
            return
        # Full, empty, switched off, hysteresis: not the temperature.
        if reason_for(command, soc, config) is not None:
            return
        charging = asked_w > 0
        if soc is not None and (
            soc <= config.min_soc + NEAR_LIMIT
            if not charging
            else soc >= min(config.max_soc, 100.0) - NEAR_LIMIT
        ):
            return
        most = config.max_charge_w if charging else config.max_discharge_w
        asked = min(abs(asked_w), most) if most > 0 else abs(asked_w)
        given = max(power_w if charging else -power_w, 0.0)
        direction = "charge" if charging else "discharge"
        band = self.bands[direction].setdefault(
            str(band_of(temperature_c)),
            {"n": 0, "limited": 0, "given_w": 0.0, "max_w": 0.0},
        )
        band["n"] += 1
        band["max_w"] = round(max(band["max_w"], given), 1)
        if given < LIMITED_SHARE * asked:
            band["limited"] += 1
            band["given_w"] = round(band["given_w"] + given, 1)

    def _add_hour(
        self,
        when: datetime,
        seconds: float,
        power_w: float | None,
        temperature_c: float | None,
        outdoor_c: float | None,
    ) -> None:
        start = when.replace(minute=0, second=0, microsecond=0)
        hour = self._hour
        if hour is not None and hour.start != start:
            self._close(hour)
            hour = None
        if hour is None:
            hour = self._hour = _Hour(start)
            return  # the first look of an hour only starts it
        if seconds <= 0:
            return
        if temperature_c is not None:
            hour.temp_cs += temperature_c * seconds
            hour.temp_s += seconds
        if outdoor_c is not None:
            hour.outdoor_cs += outdoor_c * seconds
            hour.outdoor_s += seconds
        if power_w is not None:
            hour.wh += abs(power_w) * seconds / 3600

    def _close(self, hour: _Hour) -> None:
        if hour.temp_s <= 0:
            return
        self.hours.append(
            {
                "start": hour.start.isoformat(),
                "temp_c": round(hour.temp_cs / hour.temp_s, 1),
                "outdoor_c": round(hour.outdoor_cs / hour.outdoor_s, 1)
                if hour.outdoor_s > 0
                else None,
                "kwh": round(hour.wh / 1000, 3),
            }
        )
        cutoff = (hour.start - KEEP).isoformat()
        self.hours = [h for h in self.hours if h["start"] >= cutoff]

    def summary(self) -> dict[str, Any]:
        """Per direction and band (coldest first): looks, share limited and
        what it gave on average while limited; and the temperature range."""
        out: dict[str, Any] = {}
        for direction, bands in self.bands.items():
            rows = []
            for key in sorted(bands, key=float):
                b = bands[key]
                rows.append(
                    {
                        "from_c": float(key),
                        "to_c": float(key) + BAND_C,
                        "looks": int(b["n"]),
                        "limited_pct": round(100 * b["limited"] / b["n"])
                        if b["n"]
                        else None,
                        "limited_w": round(b["given_w"] / b["limited"])
                        if b["limited"]
                        else None,
                        "max_w": b["max_w"],
                    }
                )
            out[direction] = rows
        temps = [h["temp_c"] for h in self.hours]
        out["hours"] = len(self.hours)
        out["temp_min_c"] = min(temps, default=None)
        out["temp_max_c"] = max(temps, default=None)
        return out

    def as_dict(self) -> dict[str, Any]:
        """For the store."""
        return {"bands": self.bands, "hours": self.hours}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> BatteryTemperature:
        """From the store (invalid parts dropped)."""
        result = cls()
        bands = data.get("bands") or {}
        for direction in ("charge", "discharge"):
            for key, b in (bands.get(direction) or {}).items():
                try:
                    float(key)
                    result.bands[direction][key] = {
                        "n": int(b["n"]),
                        "limited": int(b["limited"]),
                        "given_w": float(b["given_w"]),
                        "max_w": float(b["max_w"]),
                    }
                except (KeyError, TypeError, ValueError):
                    continue
        result.hours = [
            h
            for h in data.get("hours") or []
            if isinstance(h, dict) and isinstance(h.get("start"), str)
        ]
        return result


class TemperatureLearning:
    """The observations of every real battery, kept in a store."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry_id: str,
        outdoor: Callable[[], float | None] | None = None,
    ) -> None:
        """Initialize."""
        self._store: Store[dict[str, Any]] = Store(
            hass, STORAGE_VERSION, f"{DOMAIN}.{entry_id}.battery_temperature"
        )
        self._outdoor = outdoor
        self.batteries: dict[str, BatteryTemperature] = {}

    async def async_load(self) -> None:
        """Load the stored observations."""
        data = await self._store.async_load() or {}
        self.batteries = {
            battery_id: BatteryTemperature.from_dict(value)
            for battery_id, value in (data.get("batteries") or {}).items()
            if isinstance(value, dict)
        }

    async def async_save(self) -> None:
        """Write to disk now."""
        await self._store.async_save(self._data())

    def _data(self) -> dict[str, Any]:
        return {
            "batteries": {
                battery_id: value.as_dict()
                for battery_id, value in self.batteries.items()
            }
        }

    def observe(
        self,
        when: datetime,
        config: BatteryConfig,
        command: BatteryCommand | None,
        soc: float | None,
        power_w: float | None,
        temperature_c: float | None,
    ) -> None:
        """One look at a real battery (from the command check)."""
        outdoor = None
        if self._outdoor is not None:
            try:
                outdoor = self._outdoor()
            except Exception:  # an outdoor source must not stop the recording
                outdoor = None
        battery = self.batteries.setdefault(config.id, BatteryTemperature())
        battery.observe(
            dt_util.as_utc(when),
            config,
            command,
            soc,
            power_w,
            temperature_c,
            outdoor,
        )
        self._store.async_delay_save(self._data, SAVE_DELAY)

    def summary(self) -> dict[str, Any]:
        """Per battery id what was observed (diagnostics)."""
        return {
            battery_id: value.summary() for battery_id, value in self.batteries.items()
        }
