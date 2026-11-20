"""Every driver or module not tested on a real setup says so where it is
chosen: the translated option labels follow the ``verified`` flags."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from custom_components.homebatteryassist.config_flow import _own_label, untested
from custom_components.homebatteryassist.engine.control.interceptors import (
    BUILTIN as INTERCEPTORS,
)
from custom_components.homebatteryassist.engine.db_store import VERIFIED as STORAGE
from custom_components.homebatteryassist.engine.devices.inverters import (
    DRIVERS as INVERTERS,
)
from custom_components.homebatteryassist.engine.devices.meters import (
    DRIVERS as METERS,
)
from custom_components.homebatteryassist.engine.evaluation.pv_corrections import (
    BUILTIN as PV_CORRECTORS,
)
from custom_components.homebatteryassist.engine.forecast.forecasters import (
    BUILTIN as FORECASTERS,
)
from custom_components.homebatteryassist.engine.measure.spike_filters import (
    BUILTIN as SPIKE_FILTERS,
)
from custom_components.homebatteryassist.engine.planning.planners import (
    BUILTIN as PLANNERS,
)
from custom_components.homebatteryassist.engine.sources.tariffs import (
    BUILTIN as TARIFFS,
)
from custom_components.homebatteryassist.engine.sources.weather import (
    BUILTIN as WEATHER,
)

COMPONENT = Path(__file__).parent.parent / "custom_components" / "homebatteryassist"
FILES = {
    "strings.json": " (not tested)",
    "translations/en.json": " (not tested)",
    "translations/nl.json": " (niet getest)",
}


def _registry(items: Any) -> dict[str, Any]:
    if isinstance(items, dict):
        return dict(items)
    return {d.key: d for d in items}


SELECTORS = {
    "plan_mode": _registry(PLANNERS),
    "consumption_forecaster": _registry(FORECASTERS),
    "pv_corrector": _registry(PV_CORRECTORS),
    "spike_filter": _registry(SPIKE_FILTERS),
    "tariff": _registry(TARIFFS),
    "interceptor": _registry(INTERCEPTORS),
    "weather_source": _registry(WEATHER),
    "inverter_driver": _registry(INVERTERS),
    "meter_source": _registry(METERS),
    "storage_backend": {
        key: SimpleNamespace(verified=verified) for key, verified in STORAGE.items()
    },
}


@pytest.mark.parametrize("file", list(FILES))
def test_option_labels_follow_verified(file: str) -> None:
    """A built-in option ends with "(not tested)" exactly when its driver or
    module is not verified."""
    options = json.loads((COMPONENT / file).read_text(encoding="utf-8"))["selector"]
    suffix = FILES[file]
    checked = 0
    for selector, registry in SELECTORS.items():
        for key, item in registry.items():
            label = options[selector]["options"].get(key)
            assert label is not None, (file, selector, key)
            assert label.endswith(suffix) == (not item.verified), (
                file,
                selector,
                key,
                label,
            )
            checked += 1
    assert checked >= 20


def test_own_modules_say_not_tested() -> None:
    """Own modules are "not tested" until they set ``verified = True``."""
    own = SimpleNamespace(name="My planner")
    assert _own_label(own, "custom_mine", dutch=True) == "My planner (niet getest)"
    assert _own_label(own, "custom_mine", dutch=False) == "My planner (not tested)"
    tested = SimpleNamespace(name="", verified=True)
    assert _own_label(tested, "custom_mine", dutch=True) == "custom_mine"
    assert untested(True, dutch=False) == ""
