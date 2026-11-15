"""Persisted log of decisions with a human-readable explanation."""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime
from typing import Any, TypedDict

from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from ..const import DOMAIN
from .messages import render

_LOGGER = logging.getLogger(__name__)

STORAGE_VERSION = 1
SAVE_DELAY = 30  # seconds
MAX_ENTRIES = 200
EVENT_DECISION = f"{DOMAIN}_decision"


class Decision(TypedDict):
    """One decision or notable change, with its explanation."""

    time: str  # ISO 8601, UTC
    category: str  # e.g. "planning", "measurement"
    key: str  # stable identifier of the kind of decision
    params: dict[str, Any]  # JSON-serialisable details
    message: str  # explanation in the user's language


class DecisionLog:
    """Keeps the most recent decisions, persisted, and notifies listeners."""

    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        """Initialize."""
        self.hass = hass
        self._store: Store[dict[str, Any]] = Store(
            hass, STORAGE_VERSION, f"{DOMAIN}.{entry_id}.decisions"
        )
        self.entries: list[Decision] = []
        self._listeners: list[Callable[[], None]] = []

    @property
    def latest(self) -> Decision | None:
        """The most recent decision."""
        return self.entries[-1] if self.entries else None

    async def async_load(self) -> None:
        """Load stored decisions."""
        if (data := await self._store.async_load()) is not None:
            self.entries = data.get("entries", [])

    async def async_save(self) -> None:
        """Write decisions to disk now."""
        await self._store.async_save(self._data())

    @callback
    def async_add_listener(self, listener: Callable[[], None]) -> CALLBACK_TYPE:
        """Call ``listener`` after every new decision."""
        self._listeners.append(listener)
        return lambda: self._listeners.remove(listener)

    @callback
    def async_log(self, category: str, key: str, **params: Any) -> Decision:
        """Record a decision and explain it."""
        decision = Decision(
            time=dt_util.utcnow().isoformat(),
            category=category,
            key=key,
            params={k: _serialisable(v) for k, v in params.items()},
            message=render(self.hass.config.language, key, params),
        )
        self.entries.append(decision)
        del self.entries[:-MAX_ENTRIES]
        self._store.async_delay_save(self._data, SAVE_DELAY)

        _LOGGER.info("[%s] %s", category, decision["message"])
        self.hass.bus.async_fire(EVENT_DECISION, dict(decision))
        for listener in list(self._listeners):
            listener()
        return decision

    def _data(self) -> dict[str, Any]:
        return {"entries": self.entries}


def _serialisable(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    return value
