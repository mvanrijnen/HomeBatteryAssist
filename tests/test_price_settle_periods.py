"""An hourly price estimate is settled against the quarter prices of its hour."""

from datetime import timedelta

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from custom_components.homebatteryassist.engine.evaluation.forecast_accuracy import (
    ForecastAccuracy,
)


async def test_hourly_estimate_against_quarters(hass: HomeAssistant) -> None:
    accuracy = ForecastAccuracy(hass, "test")
    now = dt_util.utcnow().replace(minute=0, second=0, microsecond=0)
    start = now + timedelta(hours=10)
    accuracy.record("price", [(start, start + timedelta(hours=1), 0.30)], now)
    q = timedelta(minutes=15)
    quarters = [
        (start + i * q, start + (i + 1) * q, p)
        for i, p in enumerate((0.2, 0.3, 0.4, 0.5))
    ]
    # Only part of the hour published: not settled yet.
    assert accuracy.evaluate_prices(quarters[:2]) == 0
    assert accuracy.evaluate_prices(quarters) == 1
    result = accuracy.results["price"][-1]
    assert abs(result["actual"] - 0.35) < 1e-9
