"""Remove entities HomeBatteryAssist no longer provides.

Some entities exist only under a condition (three phases, a real battery, a
twin). Their unique ids are on the main device or on a subentry that stays,
so Home Assistant does not remove them when the condition goes away: they
would stay behind as "no longer provided". Every platform records what it
adds (``tracked``); after the platforms are set up, ``remove_stale`` removes
this entry's other entities of those platforms from the entity registry.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from ..const import DOMAIN

_LOGGER = logging.getLogger(__name__)


def tracked(entry: Any, add: Any, domain: str) -> Any:
    """``async_add_entities`` that remembers the unique ids it added."""
    provided: dict[str, set[str]] = entry.runtime_data.provided
    ids = provided.setdefault(domain, set())

    def add_and_track(entities: Iterable[Any], *args: Any, **kwargs: Any) -> None:
        entities = list(entities)
        ids.update(e.unique_id for e in entities if e.unique_id)
        add(entities, *args, **kwargs)

    return add_and_track


def remove_stale(hass: HomeAssistant, entry: Any) -> None:
    """Remove this entry's entities that a platform no longer provides
    (only of platforms that were set up this time)."""
    provided: dict[str, set[str]] = entry.runtime_data.provided
    registry = er.async_get(hass)
    for item in er.async_entries_for_config_entry(registry, entry.entry_id):
        if item.platform != DOMAIN or item.domain not in provided:
            continue
        if item.unique_id not in provided[item.domain]:
            _LOGGER.info("Removing %s: no longer provided", item.entity_id)
            registry.async_remove(item.entity_id)
