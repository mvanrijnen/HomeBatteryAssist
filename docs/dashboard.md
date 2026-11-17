# Dashboard

A dashboard in the sidebar (*HomeBatteryAssist*), in tabs. The chosen tab is remembered per browser. The title bar shows the installed version.

- **Overview**: the active planner, consumption forecaster, tariff and PV correction (with a warning on a fallback); the energy flows now (and which grid meter is used), a price tile with the market, import and export price now and from the next price change; the grid connection per phase, centred at zero (export to the left, import to the right) with a total bar on 3 phases; what phase protection and peak shaving do right now; the latest decisions (*Why*).
- **Forecast**: energy flows and expected consumption with the prices on a second axis (published solid, forecast dashed), by default over the whole forecast — or today / today + tomorrow, and browsable back into the history; the batteries' state of charge (measured and planned); the last 7 days; the average day with a line per day of the week (Mon–Sun) and the average of all days dashed, browsable per week.
- **Return**: the expected and realised return of each mode compared with no battery and with each other; the plan compared with what really happened, per day.
- **Batteries**: each battery with its state of charge, power, time to full/empty (now, by the plan and at zero on the meter) and the details its driver adds.
- **Accuracy**: the accuracy of the consumption, PV and price forecasts per lead time, with their corrections; the consumption forecasters compared; and the PV corrections compared (with the uncorrected forecast for reference).

The plan mode can be chosen right on the dashboard.
