# HomeBatteryAssist

A Home Assistant custom integration for monitoring and controlling home batteries.

> **Status:** early development. Battery control is not available yet.

HomeBatteryAssist will plan and control home batteries based on your house consumption, energy price forecasts and solar (PV) forecasts. It does not make forecasts itself: it uses the price and PV forecast integrations you already have.

## Features (so far)

- Guided setup of your grid connection: 1 or 3 phases and the connection size (1x10A up to 3x80A).
- Per-phase grid measurement from your smart meter: one signed sensor, or separate import and return sensors. Power (W) and current (A) sensors are supported.
- **PV sources** and **excluded devices** (e.g. an EV charger), each optionally bound to a phase on 3-phase connections.
- **House consumption** sensor: grid + PV production − excluded devices.
- Consumption history per 5, 15 or 60 minutes, as the basis for consumption forecasting.
- Price forecast from a price sensor (e.g. Nordpool, ENTSO-e, Frank Energie) and PV forecast from any integration that supports the Energy dashboard's solar forecast (e.g. Forecast.Solar, Solcast).
- **Planning horizon** sensor: how far ahead the system can plan, limited by your setting and by how far the forecasts reach.

## Installation

### HACS (custom repository)

1. In HACS, open the menu → **Custom repositories**.
2. Add `https://github.com/mvanrijnen/HomeBatteryAssist` with type **Integration**.
3. Install **HomeBatteryAssist** and restart Home Assistant.
4. Go to **Settings → Devices & services → Add integration** and search for **HomeBatteryAssist**.

### Manual

Copy `custom_components/homebatteryassist` into your Home Assistant `config/custom_components/` directory and restart Home Assistant.

## Why did it do that? Logging

- **Last decision** sensor: a short explanation (in your language) of the most recent decision or notable change, e.g. why the planning horizon is shorter than configured. The `recent` attribute holds the last 10.
- Every decision is also fired as the `homebatteryassist_decision` event, so you can use it in automations or notifications.
- **Diagnostics**: Settings → Devices & services → HomeBatteryAssist → ⋮ → *Download diagnostics* gives the configuration and the internal state of each module, useful when reporting an issue.
- **Technical logging** per module, e.g. in `configuration.yaml`:

  ```yaml
  logger:
    logs:
      custom_components.homebatteryassist: info               # decisions
      custom_components.homebatteryassist.forecasts: debug    # forecast details
  ```

## Development

```bash
python -m venv .venv
.venv/bin/pip install -r requirements_test.txt   # Windows: .venv\Scripts\pip
pytest
ruff check . && ruff format --check .
```
