"""Tests for consumption forecaster, tariff and PV forecast source modules."""

from datetime import datetime, timedelta
from pathlib import Path

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from custom_components.homebatteryassist.engine.forecasts.consumption import (
    forecast_consumption,
    raw_forecast,
)
from custom_components.homebatteryassist.engine.forecasts.horizon import (
    HorizonLimit,
    PlanningWindow,
)
from custom_components.homebatteryassist.engine.inputs.prices import PricePoint
from custom_components.homebatteryassist.engine.modules.forecasters import (
    BUILTIN as FORECASTERS,
)
from custom_components.homebatteryassist.engine.modules.forecasters import (
    Forecaster,
    ForecasterInput,
    ForecasterResult,
    load_forecasters_from,
)
from custom_components.homebatteryassist.engine.modules.pv_forecasts import (
    PvForecastOption,
    PvForecastSource,
    async_find_pv_forecasts,
    async_read_pv_forecasts,
    load_pv_sources_from,
    split_choice,
)
from custom_components.homebatteryassist.engine.modules.tariffs import (
    BUILTIN as TARIFFS,
)
from custom_components.homebatteryassist.engine.modules.tariffs import (
    Tariff,
    TariffInput,
    TariffResult,
    apply_tariff,
    load_tariffs_from,
)

T0 = datetime(2026, 11, 16, 12, 0, tzinfo=dt_util.UTC)  # a Monday
H = timedelta(hours=1)
PACKAGE = Path(__file__).parent.parent / "custom_components/homebatteryassist"


def _history(days: int = 21, watts: float = 500.0) -> list[dict]:
    return [
        {
            "start": (T0 - timedelta(hours=h)).isoformat(),
            "minutes": 60,
            "avg_w": watts,
            "coverage": 1.0,
        }
        for h in range(1, days * 24 + 1)
    ]


def _window(hours: int = 4) -> PlanningWindow:
    return PlanningWindow(T0, T0 + hours * H, HorizonLimit.SETTING)


# -- consumption forecasters ---------------------------------------------------


class Wild(Forecaster):
    """Nonsense in every way."""

    key = "wild"

    def forecast(self, data: ForecasterInput) -> list:
        return [-5.0, float("inf"), 10_000_000.0, "abc"]


def test_builtin_forecasters() -> None:
    """The profile and the last weeks are built in; both predict a steady house."""
    assert set(FORECASTERS) == {"profile", "last_weeks"}
    for forecaster in FORECASTERS.values():
        slots = raw_forecast(forecaster, _history(), _window(), H, T0)
        assert [round(v) for _, _, v, _ in slots] == [500, 500, 500, 500]


def test_forecaster_final_check() -> None:
    """Missing, negative and absurd values are replaced by the profile."""
    slots = raw_forecast(Wild(), _history(), _window(), H, T0)
    assert [v for _, _, v, _ in slots] == [500.0] * 4
    assert all(method != "wild" for _, _, _, method in slots)


def test_forecaster_drives_consumption() -> None:
    """The chosen forecaster's values are the forecast, its key the method."""

    class Fixed(Forecaster):
        key = "fixed"

        def forecast(self, data: ForecasterInput) -> ForecasterResult:
            return ForecasterResult([800.0] * len(data.slots))

    slots = forecast_consumption(_history(), _window(), H, now=T0, forecaster=Fixed())
    assert [s.power_w for s in slots] == [800.0] * 4
    assert slots[0].method == "fixed"


def test_load_own_forecasters(tmp_path: Path) -> None:
    """The template loads as an own forecaster."""
    template = PACKAGE / "engine/modules/forecasters/template.py"
    (tmp_path / "mine.py").write_text(
        template.read_text(encoding="utf-8"), encoding="utf-8"
    )
    found = load_forecasters_from(tmp_path)
    assert list(found) == ["custom_last_day_average"]
    slots = raw_forecast(found["custom_last_day_average"], _history(), _window(), H, T0)
    assert [v for _, _, v, _ in slots] == [500.0] * 4


# -- tariffs ------------------------------------------------------------------


def _prices() -> list[PricePoint]:
    return [
        PricePoint(T0 + i * H, T0 + (i + 1) * H, p, i > 1)
        for i, p in enumerate([0.30, 0.25, 0.40, 0.35])
    ]


def test_source_tariff_keeps_prices() -> None:
    """The built-in tariff keeps import prices; export by the factor."""
    imports, exports = apply_tariff(
        TARIFFS["source"], _prices(), [], [], T0, "EUR/kWh", 0.25
    )
    assert [p.price for p in imports] == [0.30, 0.25, 0.40, 0.35]
    assert [p.estimated for p in imports] == [False, False, True, True]
    assert [round(p.price, 4) for p in exports] == [0.075, 0.0625, 0.1, 0.0875]


def test_tariff_final_check() -> None:
    """Missing or absurd tariff prices fall back to the source's."""

    class Odd(Tariff):
        key = "odd"

        def prices(self, data: TariffInput) -> TariffResult:
            return TariffResult([1.0, None, 99.0], [0.1, float("nan")])

    imports, exports = apply_tariff(Odd(), _prices(), [], [], T0, None, 1.0)
    assert [p.price for p in imports] == [1.0, 0.25, 0.40, 0.35]
    assert [p.price for p in exports] == [0.1, 0.25, 0.40, 0.35]


def test_own_tariff_with_market_prices(tmp_path: Path) -> None:
    """The template tariff builds prices from the market price."""
    template = PACKAGE / "engine/modules/tariffs/template.py"
    (tmp_path / "contract.py").write_text(
        template.read_text(encoding="utf-8"), encoding="utf-8"
    )
    found = load_tariffs_from(tmp_path)
    tariff = found["custom_dynamic_contract"]
    assert tariff.needs_market
    market = [PricePoint(T0, T0 + H, 0.10)]
    imports, exports = apply_tariff(tariff, _prices(), [], market, T0, None, 1.0)
    # (0.10 + 0.02 + 0.10) x 1.21; without a market price the source's price.
    assert imports[0].price == round(0.22 * 1.21, 5)
    assert imports[1].price == 0.25
    assert exports[0].price == 0.08


# -- PV forecast sources ---------------------------------------------------------


class Flat(PvForecastSource):
    key = "flat"
    name = "Flat"

    async def async_find(self, hass: HomeAssistant) -> list[PvForecastOption]:
        return [PvForecastOption("roof", "Roof")]

    async def async_read(self, hass: HomeAssistant, option_id: str) -> dict:
        return {
            T0: 1000.0,
            T0 + H: -5.0,  # dropped
            datetime(2026, 11, 16, 14, 0): 500.0,  # no time zone: dropped
            T0 + 3 * H: float("nan"),  # dropped
        }


async def test_pv_sources(hass: HomeAssistant) -> None:
    """Own sources are offered next to the integrations and checked when read."""
    own = {"custom_flat": Flat()}
    found = await async_find_pv_forecasts(hass, own)
    assert ("custom_flat:roof", "Roof (Flat)") in found
    assert split_choice("custom_flat:roof") == ("custom_flat", "roof")
    assert split_choice("01ABC") == ("energy", "01ABC")  # older settings
    total = await async_read_pv_forecasts(
        hass, ["custom_flat:roof", "custom_flat:roof", "missing:x"], own
    )
    assert total == {T0: 2000.0}


def test_load_own_pv_sources(tmp_path: Path) -> None:
    """The template loads as an own PV forecast source."""
    template = PACKAGE / "engine/modules/pv_forecasts/template.py"
    (tmp_path / "sensor.py").write_text(
        template.read_text(encoding="utf-8"), encoding="utf-8"
    )
    assert list(load_pv_sources_from(tmp_path)) == ["custom_sensor_wh_hours"]
