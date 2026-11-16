"""Price drivers for core integrations that give prices through an action.

Nord Pool, EnergyZero and easyEnergy (all part of Home Assistant) do
not keep a price list in their sensors; they offer a read-only action with a
response instead. The drivers call it for today and tomorrow, at most every
``REFRESH`` per source (the integrations fetch from the supplier's API).

Implemented from the Home Assistant documentation of these actions; not yet
verified on a real installation.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from datetime import datetime, timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.util import dt as dt_util

from ...units import parse_float, parse_time
from .base import (
    ROLE_EXPORT,
    ROLE_IMPORT,
    ROLE_MARKET,
    PriceData,
    PriceDriver,
    PriceSource,
)
from .price_points import PricePoint

_LOGGER = logging.getLogger(__name__)

REFRESH = timedelta(hours=1)


def points_from(
    items: Iterable[tuple[Any, Any, Any]], scale: float = 1.0
) -> list[PricePoint]:
    """(start, end or None, price) tuples -> sorted price points per kWh."""
    raw = []
    for start, end, price in items:
        when = parse_time(start)
        value = parse_float(price)
        if when is None or value is None:
            continue
        raw.append((when, parse_time(end) if end else None, value * scale))
    raw.sort(key=lambda item: item[0])
    points = []
    for index, (start, end, price) in enumerate(raw):
        if end is None:
            if index + 1 < len(raw):
                end = raw[index + 1][0]
            elif index:
                end = start + (start - raw[index - 1][0])
            else:
                end = start + timedelta(hours=1)
        points.append(PricePoint(start, end, round(price, 6)))
    return points


class ActionDriver(PriceDriver):
    """Base for drivers that read prices through an action with a response."""

    domain = ""

    def __init__(self) -> None:
        """Initialize the cache: (source, role) -> (fetched at, data)."""
        self._cache: dict[tuple[str, str], tuple[datetime, PriceData]] = {}

    def find(self, hass: HomeAssistant) -> list[PriceSource]:
        """One source per loaded config entry of the integration."""
        return [
            PriceSource(
                self.key, entry.entry_id, f"{self.name}: {entry.title}", self.roles, 2
            )
            for entry in hass.config_entries.async_loaded_entries(self.domain)
        ]

    roles: frozenset[str] = frozenset({ROLE_IMPORT})

    async def async_read(
        self, hass: HomeAssistant, source: str, role: str
    ) -> PriceData:
        """Cached prices; fetched again after ``REFRESH``, or when tomorrow is
        still missing in the afternoon."""
        now = dt_util.utcnow()
        cached = self._cache.get((source, role))
        if cached is not None:
            fetched, data = cached
            tomorrow = dt_util.start_of_local_day() + timedelta(days=2)
            complete = bool(data.points) and data.points[-1].end >= tomorrow
            if now - fetched < REFRESH and (
                complete or dt_util.as_local(now).hour < 13
            ):
                return data
        try:
            data = await self._async_fetch(hass, source, role)
        except (HomeAssistantError, KeyError, TypeError, ValueError) as err:
            _LOGGER.debug("%s: no prices for %s: %s", self.name, source, err)
            return cached[1] if cached else PriceData([])
        self._cache[(source, role)] = (now, data)
        return data

    async def _async_fetch(
        self, hass: HomeAssistant, source: str, role: str
    ) -> PriceData:
        raise NotImplementedError

    @staticmethod
    async def _call(
        hass: HomeAssistant, domain: str, service: str, data: dict[str, Any]
    ) -> dict[str, Any]:
        return await hass.services.async_call(
            domain, service, data, blocking=True, return_response=True
        )  # type: ignore[return-value]


def _days() -> tuple[datetime, datetime]:
    start = dt_util.start_of_local_day()
    return start, start + timedelta(days=2)


class NordPoolDriver(ActionDriver):
    """Nord Pool (core): ``nordpool.get_prices_for_date``, per MWh."""

    key = "nordpool"
    name = "Nord Pool"
    domain = "nordpool"
    roles = frozenset({ROLE_MARKET, ROLE_IMPORT})

    async def _async_fetch(
        self, hass: HomeAssistant, source: str, role: str
    ) -> PriceData:
        start, _ = _days()
        items = []
        currency = None
        for offset in (0, 1):
            day = (start + timedelta(days=offset)).date().isoformat()
            response = await self._call(
                hass,
                "nordpool",
                "get_prices_for_date",
                {"config_entry": source, "date": day},
            )
            for area_prices in response.values():
                items += [
                    (p.get("start"), p.get("end"), p.get("price")) for p in area_prices
                ]
                break  # the first (configured) area
        entry = hass.config_entries.async_get_entry(source)
        if entry is not None:
            currency = entry.data.get("currency")
        unit = f"{currency}/kWh" if currency else None
        return PriceData(points_from(items, 1 / 1000), unit)


class EnergyZeroDriver(ActionDriver):
    """EnergyZero (core): ``energyzero.get_energy_prices`` incl. VAT."""

    key = "energyzero"
    name = "EnergyZero"
    domain = "energyzero"
    service = "get_energy_prices"

    async def _async_fetch(
        self, hass: HomeAssistant, source: str, role: str
    ) -> PriceData:
        start, end = _days()
        response = await self._call(
            hass,
            self.domain,
            self._service(role),
            {
                "config_entry": source,
                "incl_vat": True,
                "start": start.isoformat(),
                "end": end.isoformat(),
            },
        )
        return PriceData(
            points_from(
                (p.get("timestamp"), None, p.get("price"))
                for p in response.get("prices", [])
            ),
            "EUR/kWh",
        )

    def _service(self, role: str) -> str:
        return self.service


class EasyEnergyDriver(EnergyZeroDriver):
    """easyEnergy (core): usage and return (export) prices incl. VAT."""

    key = "easyenergy"
    name = "easyEnergy"
    domain = "easyenergy"
    roles = frozenset({ROLE_IMPORT, ROLE_EXPORT})

    def _service(self, role: str) -> str:
        return (
            "get_energy_return_prices"
            if role == ROLE_EXPORT
            else "get_energy_usage_prices"
        )


ACTION_DRIVERS: tuple[PriceDriver, ...] = (
    NordPoolDriver(),
    EnergyZeroDriver(),
    EasyEnergyDriver(),
)
