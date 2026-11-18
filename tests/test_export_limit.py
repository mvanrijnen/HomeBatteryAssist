"""Tests for the export limit (PV inverters): shown and explained only."""

from datetime import UTC, datetime, timedelta

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.homebatteryassist.const import (
    CONF_HISTORY_INTERVAL,
    CONF_MAX_CURRENT,
    CONF_PHASES,
    DOMAIN,
)
from custom_components.homebatteryassist.engine.control.export_limiter import (
    ExportLimiter,
)
from custom_components.homebatteryassist.engine.devices.inverters import get_driver
from custom_components.homebatteryassist.engine.planning.export_limit import (
    connection_w,
    export_limit,
)

NOW = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)
CONNECTION = connection_w(3, 25)  # 17250 W


def test_export_limit_rule() -> None:
    """Below the price: 0 W; else a fixed maximum; else the connection."""
    rule = {"enabled": True, "threshold": 0.0, "fixed_w": 0.0}
    limit = export_limit(price=-0.05, connection=CONNECTION, **rule)
    assert (limit.limit_w, limit.limited, limit.reason) == (0.0, True, "price")
    limit = export_limit(price=0.08, connection=CONNECTION, **rule)
    assert (limit.limit_w, limit.limited) == (CONNECTION, False)
    assert round(limit.amps_per_phase(3)) == 25
    limit = export_limit(price=None, connection=CONNECTION, **rule)
    assert not limit.limited  # price unknown: not limited by price
    fixed = {**rule, "fixed_w": 5000.0}
    limit = export_limit(price=0.08, connection=CONNECTION, **fixed)
    assert (limit.limit_w, limit.reason) == (5000.0, "fixed")
    limit = export_limit(price=-0.01, connection=CONNECTION, **fixed)
    assert limit.limit_w == 0.0  # the price wins
    off = {**rule, "enabled": False}
    assert not export_limit(price=-0.5, connection=CONNECTION, **off).limited


class _Log:
    def __init__(self) -> None:
        self.keys: list[tuple[str, dict]] = []

    def async_log(self, _category: str, key: str, **params) -> None:
        self.keys.append((key, params))


def test_limiter_explains_what_it_would_curtail() -> None:
    """Exporting 2000 W at a negative price: the inverters would produce
    2000 W less; told once, and when it ends with the energy and value."""
    log = _Log()
    limiter = ExportLimiter(
        log,  # type: ignore[arg-type]
        enabled=True,
        threshold=0.0,
        fixed_w=0.0,
        connection=CONNECTION,
        inverters=[("SMA", get_driver("sma_modbus"), "192.168.1.10")],
    )
    when = NOW
    for _ in range(60):  # a value a minute; with the last one: 1 hour
        limiter.update(when, -2000.0, -0.10)
        when += timedelta(minutes=1)
    assert limiter.limit.limit_w == 0.0
    assert limiter.curtailed_w == 2000.0
    assert [k for k, _ in log.keys] == ["export_limit_started"]
    assert limiter.would_send() == ["SMA Modbus 192.168.1.10: 40151=802, 40149=0"]
    # The price turns positive: no limit, the episode ends.
    limiter.update(when, -2000.0, 0.05)
    assert not limiter.limit.limited and limiter.curtailed_w == 0.0
    key, params = log.keys[-1]
    assert key == "export_limit_ended"
    assert params["energy"] == "2.00"  # 2000 W for an hour
    assert params["value"] == "0.20"  # paying 0.10/kWh avoided
    assert round(limiter.today_kwh, 2) == 2.0


def test_limiter_small_export_is_not_curtailed() -> None:
    """Export below the minimum, or importing: nothing to curtail."""
    log = _Log()
    limiter = ExportLimiter(
        log,  # type: ignore[arg-type]
        enabled=True,
        threshold=0.0,
        fixed_w=0.0,
        connection=CONNECTION,
        inverters=[],
    )
    limiter.update(NOW, -20.0, -0.10)
    limiter.update(NOW + timedelta(seconds=5), 500.0, -0.10)
    assert limiter.limit.limited and limiter.curtailed_w == 0.0
    assert log.keys == []


async def test_max_export_sensor(hass: HomeAssistant) -> None:
    """The sensor on the grid connection: the connection's maximum when not
    limited, and not controlled."""
    hass.states.async_set("sensor.l1", "-500", {"unit_of_measurement": "W"})
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_PHASES: 1, CONF_MAX_CURRENT: 35, "sensor_l1": "sensor.l1"},
        options={CONF_HISTORY_INTERVAL: 15},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    hass.states.async_set("sensor.l1", "-600", {"unit_of_measurement": "W"})
    await hass.async_block_till_done()
    entity_id = er.async_get(hass).async_get_entity_id(
        "sensor", DOMAIN, f"{entry.entry_id}_export_limit"
    )
    state = hass.states.get(entity_id)
    assert float(state.state) == connection_w(1, 35)
    assert state.attributes["limited"] is False
    assert state.attributes["controlled"] is False
