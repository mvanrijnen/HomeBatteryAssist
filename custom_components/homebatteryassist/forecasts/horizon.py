"""Planning horizon: the configured maximum, limited by the available forecasts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum


class HorizonLimit(StrEnum):
    """What determines the end of the planning horizon."""

    SETTING = "setting"  # the configured maximum number of days
    PRICE = "price"  # the price forecast ends earlier
    PV = "pv"  # the PV forecast ends earlier
    NO_PRICE = "no_price"  # price forecast configured, but no data
    NO_PV = "no_pv"  # PV forecast configured, but no data


@dataclass(frozen=True, slots=True)
class Horizon:
    """End of the planning horizon and why it ends there."""

    end: datetime
    limited_by: HorizonLimit


def planning_horizon(
    now: datetime,
    max_days: int,
    price_end: datetime | None,
    pv_end: datetime | None,
    *,
    price_configured: bool,
    pv_configured: bool,
) -> Horizon:
    """Return min(now + max_days, price forecast end, PV forecast end).

    Only configured forecasts limit the horizon. A configured forecast without
    data limits the horizon to ``now`` (no planning possible).
    """
    horizon = Horizon(now + timedelta(days=max_days), HorizonLimit.SETTING)
    for configured, forecast_end, limit, missing in (
        (price_configured, price_end, HorizonLimit.PRICE, HorizonLimit.NO_PRICE),
        (pv_configured, pv_end, HorizonLimit.PV, HorizonLimit.NO_PV),
    ):
        if not configured:
            continue
        if forecast_end is None or forecast_end <= now:
            return Horizon(now, missing)
        if forecast_end < horizon.end:
            horizon = Horizon(forecast_end, limit)
    return horizon
