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
    # A fixed contract with an export fee: 0.07 earned - 0.09 costs < 0.
    limit = export_limit(price=0.07, cost=0.09, connection=CONNECTION, **rule)
    assert (limit.limit_w, limit.reason) == (0.0, "price")
    limit = export_limit(price=0.12, cost=0.09, connection=CONNECTION, **rule)
    assert not limit.limited  # still earns 0.03 per kWh
    # Never export: always 0 W, also at a good price.
    limit = export_limit(price=0.30, never=True, connection=CONNECTION, **rule)
    assert (limit.limit_w, limit.reason) == (0.0, "never")
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


def test_possible_pv_power() -> None:
    """A PV source that could produce more than it does: the difference is
    held back, and learning uses what the sun gave."""
    from custom_components.homebatteryassist.engine.measure.house_measurement import (
        PowerFlow,
    )

    flow = PowerFlow(0.0, 1500.0, 0.0, 0.0, 1500.0, (0.0,), pv_possible_w=4000.0)
    assert flow.pv_potential_w == 4000.0
    assert flow.pv_curtailed_w == 2500.0
    plain = PowerFlow(0.0, 1500.0, 0.0, 0.0, 1500.0, (0.0,))
    assert plain.pv_potential_w == 1500.0 and plain.pv_curtailed_w == 0.0


async def test_possible_pv_sensor_in_the_flow(hass: HomeAssistant) -> None:
    """The possible-power sensor of a PV source feeds ``pv_possible_w``."""
    from homeassistant.config_entries import ConfigSubentryData

    hass.states.async_set("sensor.l1", "0", {"unit_of_measurement": "W"})
    hass.states.async_set("sensor.pv", "1500", {"unit_of_measurement": "W"})
    hass.states.async_set("sensor.pv_possible", "4000", {"unit_of_measurement": "W"})
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_PHASES: 1, CONF_MAX_CURRENT: 35, "sensor_l1": "sensor.l1"},
        options={CONF_HISTORY_INTERVAL: 15},
        subentries_data=[
            ConfigSubentryData(
                data={
                    "name": "Roof",
                    "sensor": "sensor.pv",
                    "possible_sensor": "sensor.pv_possible",
                },
                subentry_type="pv_source",
                title="Roof",
                unique_id="sensor.pv",
            )
        ],
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    hass.states.async_set("sensor.pv_possible", "4100", {"unit_of_measurement": "W"})
    await hass.async_block_till_done()
    flow = entry.runtime_data.measurements.flow
    assert flow.pv_w == 1500.0
    assert flow.pv_possible_w == 4100.0
    assert flow.house_w == 1500.0  # the house is measured, not possible


def test_expected_limits_from_the_plan() -> None:
    """Export planned at a negative price for 2 hours: one clear period,
    told once in Why; a short or tiny one is not told."""
    from types import SimpleNamespace

    def slot(hour: int, grid_w: float, price: float) -> SimpleNamespace:
        start = NOW + timedelta(hours=hour)
        return SimpleNamespace(
            start=start,
            end=start + timedelta(hours=1),
            grid_w=grid_w,
            price=price,
            export_price=price,
        )

    slots = [
        slot(0, -500, 0.10),  # earns: no limit
        slot(1, -1500, -0.02),
        slot(2, -2500, -0.05),
        slot(3, 300, -0.05),  # importing: nothing to hold back
        slot(4, -200, -0.01),  # 1 hour but only 0.2 kWh: not clear
    ]
    log = _Log()
    limiter = ExportLimiter(
        log,  # type: ignore[arg-type]
        enabled=True,
        threshold=0.0,
        fixed_w=0.0,
        connection=CONNECTION,
        inverters=[],
    )
    limiter.plan_updated(slots, NOW)
    assert len(limiter.expected) == 1
    period = limiter.expected[0]
    assert (period.start, period.end) == (
        NOW + timedelta(hours=1),
        NOW + timedelta(hours=3),
    )
    assert period.kwh == 4.0 and period.lowest_price == -0.05
    assert [k for k, _ in log.keys] == ["export_limit_expected"]
    limiter.plan_updated(slots, NOW + timedelta(minutes=5))
    assert len(log.keys) == 1  # told once
