"""Are the sensors HomeBatteryAssist uses kept by Home Assistant's recorder?

The history import (``import_history``) and the temperature import at start
fill the past from the recorder's history and statistics; a sensor the
recorder leaves out (``recorder: exclude:``) cannot be filled in. Then a
repair issue names those sensors; it goes away when they are recorded again.
"""

from __future__ import annotations

from collections.abc import Iterable

from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir

from ...const import DOMAIN

ISSUE = "recorder_excluded_sensors"


def not_recorded(hass: HomeAssistant, entity_ids: Iterable[str]) -> list[str]:
    """The sensors the recorder does not keep ([] without a recorder)."""
    if "recorder" not in hass.config.components:
        return []
    from homeassistant.components.recorder import (
        is_entity_recorded,
    )

    try:
        return sorted({e for e in entity_ids if e and not is_entity_recorded(hass, e)})
    except (KeyError, RuntimeError):  # recorder not ready
        return []


def check_recorder(
    hass: HomeAssistant, entry_id: str, entity_ids: Iterable[str]
) -> list[str]:
    """Create or clear the repair issue; returns the sensors left out."""
    missing = not_recorded(hass, entity_ids)
    issue_id = f"{ISSUE}_{entry_id}"
    if missing:
        ir.async_create_issue(
            hass,
            DOMAIN,
            issue_id,
            is_fixable=False,
            severity=ir.IssueSeverity.WARNING,
            translation_key=ISSUE,
            translation_placeholders={"sensors": ", ".join(missing)},
        )
    else:
        ir.async_delete_issue(hass, DOMAIN, issue_id)
    return missing
