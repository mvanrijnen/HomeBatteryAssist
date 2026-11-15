# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

HomeBatteryAssist is a **Home Assistant custom integration** (not an add-on/Docker container), distributed via HACS, that will plan and control home batteries using house consumption history, energy price forecasts and PV forecasts. Comparable project: Omnibattery (`ffunes/Omnibattery`).

- Domain `homebatteryassist`, display name **HomeBatteryAssist**, single config entry (`single_config_entry` in manifest).
- Built incrementally. Battery-specific support (brands, device communication) is deliberately deferred to the second half of the project — do not add brand-specific code until asked.
- Forecasts are **not** made by this integration; it consumes them from other integrations.
- Will be published: keep README, user-facing text and translations release-quality. Repo: https://github.com/mvanrijnen/HomeBatteryAssist (currently private; branch `main`). No LICENSE yet.

## Architecture

The integration is split into modules with a one-way data flow. Keep new code in the right module and do not import "upstream" (e.g. `inputs` must not import `forecasts` or `output`):

```
inputs  ->  history  ->  forecasts  ->  (planning, later)  ->  output
explain (decision log, "why") and Python logging are used by all modules
```

`__init__.py` only wires the modules of a config entry into `HomeBatteryAssistData` (`models.py`, on `entry.runtime_data`): `decisions`, `measurements`, `history`, `forecast`. Root platform files (`sensor.py`) only delegate to `output/`, because HA looks for platforms in the package root.

- **`inputs/`** — reads and normalises external data; never forecasts or decides.
  - `units.py`: `state_to_watts` (W/kW/MW, A/mA × `NOMINAL_VOLTAGE` 230 V), `parse_time`, `parse_float`.
  - `measurements.py`: `MeasurementInput`, event-driven (state change listener, no polling). `house = Σ grid phases + Σ PV sources − Σ excluded loads`, floored at 0 W. Grid per phase: one signed sensor (+import/−export) or import minus optional separate return sensor; PV/excluded use absolute values. Unknown grid sensor → consumption unknown (`missing` lists them); unknown PV/excluded → 0 W. Listeners receive `(time, power)`.
  - `prices.py`: `parse_price_forecast` reads a price sensor's attributes in common formats (lists of dicts with start/end/price-like keys under `prices`, `raw_today`/`raw_tomorrow`, `forecast`, ...; or `{timestamp: price}`). Unit = the source sensor's unit.
  - `solar.py`: PV forecast via the Energy dashboard solar forecast platform (`<domain>/energy.py` → `async_get_solar_forecast` → `wh_hours`); multiple entries summed per hour.
- **`history/`** — `ConsumptionHistory`: time-weighted average per clock-aligned interval (5/15/60 min), own boundary timer, `Store` `.storage/homebatteryassist.<entry_id>.consumption`, pruned after 28 days, `coverage` per record. Roll-over is idempotent and handles late/missed boundaries; gaps count as unmeasured. Basis for the future consumption forecast.
- **`forecasts/`** — derived knowledge about the future.
  - **Rule: every forward-looking calculation first determines the `PlanningWindow` and never calculates beyond `window.end`.** New forecast/planning code takes the window as a parameter (use `window.slots(step)` / `window.overlaps(start, end)`), and does nothing when `window.is_empty`.
  - `horizon.py`: `planning_horizon` → `PlanningWindow(start=now, end, limited_by: HorizonLimit)`, end = min(now + configured days, price end, PV end); a configured forecast without future data → empty window (`NO_PRICE`/`NO_PV`). Exposes `hours`, `duration`, `slots()`, `overlaps()`.
  - `coordinator.py`: `ForecastCoordinator` (`DataUpdateCoordinator`, 15 min + refresh on price-sensor change) runs each cycle in fixed order: 1) read inputs, 2) determine the window, 3) calculate/clip everything to the window. `ForecastData.prices`/`pv_wh` are already limited to the window; `price_end`/`pv_end` show how far the raw inputs reach.
- **`output/`** — entities. `sensors.py`: `House consumption` (W), diagnostic `Planning horizon` (timestamp = window end; attributes `hours_ahead`, `days_ahead`, `limited_by`, ...), `Last decision` (explanation; `recent` attribute). Common base `HomeBatteryAssistEntity` (one service device, unique id `<entry_id>_<key>`, translation key = key). Battery control will go here.
- **`explain/`** — the decision log ("why"), separate from technical logging. `DecisionLog.async_log(category, key, **params)` renders a message from `messages.py` in `hass.config.language` (nl/en, fallback en), persists the last 200 (`.storage/homebatteryassist.<entry_id>.decisions`), logs it at INFO, fires event `homebatteryassist_decision`, and notifies the `Last decision` sensor. Log only *changes* worth explaining (e.g. horizon limit changes, measurement lost/restored — not the first state after start-up). Every message key must exist in all languages (tested).
- **Technical logging** — `_LOGGER = logging.getLogger(__name__)` in every module (so users can set levels per module); details at DEBUG. `diagnostics.py` provides the diagnostics download with config and the state of each module.

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
