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
