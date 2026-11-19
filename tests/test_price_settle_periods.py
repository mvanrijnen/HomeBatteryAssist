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


async def test_one_wild_price_does_not_set_the_bias(hass: HomeAssistant) -> None:
    """Errors of 1 ct and one of 2 euro: the bias stays near 1 ct."""
    accuracy = ForecastAccuracy(hass, "test")
    now = dt_util.utcnow().replace(minute=0, second=0, microsecond=0)
    results = [
        {
            "start": (now - timedelta(hours=i + 1)).isoformat(),
            "actual": 0.30,
            "pred": {"6-24h": 0.31},
        }
        for i in range(60)
    ]
    results.append({"start": now.isoformat(), "actual": 2.30, "pred": {"6-24h": 0.30}})
    accuracy.results["price"] = results
    accuracy.refresh_stats(now)
    stats = accuracy.stats("price")["6-24h"]
    assert abs(stats.bias) < 0.015  # without the cap: about -0.023
    assert stats.mae > 0.03  # the shown error stays the real one


def test_published_price_far_from_the_estimate() -> None:
    from custom_components.homebatteryassist.engine.evaluation.price_surprise import (
        PriceSurprises,
    )

    now = dt_util.utcnow().replace(minute=0, second=0, microsecond=0)
    hour = timedelta(hours=1)
    a, b = now + 10 * hour, now + 11 * hour
    surprises = PriceSurprises()
    surprises.remember([(a, a + hour, 0.25), (b, b + hour, 0.25)])
    # Not published yet: nothing.
    assert surprises.check([], now) == []
    q = timedelta(minutes=15)
    published = [(a + i * q, a + (i + 1) * q, 0.27) for i in range(4)]
    published += [(b + i * q, b + (i + 1) * q, 0.60) for i in range(4)]
    found = surprises.check(published, now)
    assert [s.start for s in found] == [b]  # 2 ct off is no surprise
    assert abs(found[0].difference - 0.35) < 1e-9
    assert surprises.check(published, now) == []  # told once
