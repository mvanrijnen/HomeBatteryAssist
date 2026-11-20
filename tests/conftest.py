"""Shared fixtures for HomeBatteryAssist tests."""

import pytest


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Allow Home Assistant to load integrations from custom_components/."""
    return


@pytest.fixture(autouse=True)
def no_speedwire_discovery():
    """Tests have no network: no SMA meters to discover (sockets are blocked)."""
    from unittest.mock import AsyncMock, patch

    with patch(
        "custom_components.homebatteryassist.config_flow.discover_speedwire",
        AsyncMock(return_value={}),
    ) as mock:
        yield mock


@pytest.fixture(autouse=True)
def grid_not_frozen(request):
    """Tests set a grid sensor once and jump ahead in time: a real sensor is
    reported anew all the time, so the frozen check stays out of the way
    (tests marked ``frozen_grid`` keep it)."""
    from datetime import timedelta
    from unittest.mock import patch

    if request.node.get_closest_marker("frozen_grid"):
        yield
        return
    with patch(
        "custom_components.homebatteryassist.engine.measure.house_measurement.GRID_STALE",
        timedelta(days=3650),
    ):
        yield
