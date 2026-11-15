# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

HomeBatteryAssist is a **Home Assistant custom integration** (not an add-on/Docker container), distributed via HACS, that will plan and control home batteries using house consumption history, energy price forecasts and PV forecasts. Comparable project: Omnibattery (`ffunes/Omnibattery`).

- Domain `homebatteryassist`, display name **HomeBatteryAssist**, single config entry (`single_config_entry` in manifest).
- Built incrementally. Battery-specific support (brands, device communication) is deliberately deferred to the second half of the project — do not add brand-specific code until asked.
- Forecasts are **not** made by this integration; it consumes them from other integrations.
- Will be published: keep README, user-facing text and translations release-quality. Repo: https://github.com/mvanrijnen/HomeBatteryAssist (currently private; branch `main`). No LICENSE yet.

## Architecture

`__init__.py` builds a `HomeBatteryAssistData` (`models.py`) on `entry.runtime_data`, holding two independent parts, then forwards to `sensor.py`:

- **`HouseConsumption`** (`consumption.py`), event-driven, no polling. Listens to state changes of all source sensors and computes
  `house = Σ grid phases + Σ PV sources − Σ excluded loads`, floored at 0 W. Grid per phase is either one signed sensor (+import/−export) or an import sensor minus an optional separate return sensor; PV and excluded loads use absolute values. `state_to_watts` converts W/kW/MW and A/mA (× `NOMINAL_VOLTAGE` 230 V). Unknown grid phase → consumption unknown; unknown PV/excluded → 0 W. Every value is fed to:
- **`ConsumptionHistory`** (`history.py`): time-weighted average per clock-aligned interval (5/15/60 min), persisted with `helpers.storage.Store` (`.storage/homebatteryassist.<entry_id>.consumption`), pruned after `HISTORY_RETENTION` (28 days). Records carry `coverage` (fraction measured). Interval roll-over is idempotent and handles late/missed boundaries; gaps count as unmeasured. This is the data source for the future consumption forecast.
- **`ForecastCoordinator`** (`forecast.py`), a `DataUpdateCoordinator` (15 min, plus refresh on price-sensor state change):
  - Prices: parsed from the attributes of a user-chosen sensor (`parse_price_forecast`), recognising common formats — lists of dicts with start/end/price-like keys under attributes such as `prices`, `raw_today`/`raw_tomorrow`, `forecast`, or `{timestamp: price}` mappings. Price unit is whatever the source sensor uses.
  - PV: via the Energy dashboard solar forecast platform (`<domain>/energy.py` → `async_get_solar_forecast`, returns `wh_hours`), so any integration supported by the Energy dashboard works; multiple entries are summed per hour.
  - `planning_horizon_end`: min(now + configured days, price forecast end, PV forecast end); a configured forecast without data limits the horizon to now.
- Sensors: `House consumption` (W) and diagnostic `Planning horizon` (timestamp, with forecast-end attributes).

### Configuration model

- `entry.data` (fixed, config flow steps 1–3): `phases` (1/3); `max_current_per_phase`, restricted by `MAX_CURRENT_OPTIONS` (1x10/25/35A, 3x25/35/50/63/80A; defaults 1x35A, 3x25A); `sensor_l1..l3` + optional `return_l1..l3`.
- `entry.options` (step 4 `settings` and the options flow, same `settings_schema`): `history_interval`, `planning_horizon_days` (1–7, default 2), optional `price_forecast_entity`, optional `pv_forecast_entries` (list of config entry ids; field only shown if a solar forecast integration is loaded).
- Subentries (any number, added under the integration in the UI, with reconfigure): `pv_source` and `excluded_load` (e.g. EV charger). Data: `name`, `sensor`, `phase` (`none`/`l1`–`l3`; field only on 3-phase). A sensor may not be a grid sensor or be used by another subentry.
- Any options or subentry change reloads the entry (update listener). Unload awaits `HouseConsumption.async_stop()` so history is saved before the reload reads it.
- Every new config text must be added to `strings.json`, `translations/en.json` (identical copy) and `translations/nl.json`. Custom integrations can't use `[%key:...%]` references — write literal text.

## Commands

Home Assistant's test harness does not run on native Windows (`fcntl`); on Windows, lint and test in WSL. Machine-specific paths and live-instance details are in `CLAUDE.local.md` (not committed).

```bash
python -m venv .venv && .venv/bin/pip install -r requirements_test.txt   # Linux/WSL/macOS
ruff format . && ruff check .
pytest -q                                                       # all tests
pytest -q tests/test_forecast.py::test_planning_horizon_end     # single test
```

CI (`.github/workflows/validate.yml`) runs hassfest, HACS validation, ruff and pytest on Python 3.14. `hacs.json` declares minimum HA 2025.6.0 (needed for config subentries).
