# Development

```bash
python -m venv .venv
.venv/bin/pip install -r requirements_test.txt   # Windows: .venv\Scripts\pip
pytest
ruff check . && ruff format --check .
```

Home Assistant's test harness does not run on native Windows; use WSL there.

CI (`.github/workflows/validate.yml`) runs hassfest, HACS validation, ruff and pytest.

## Where things are

The integration is split into modules with a one-way data flow: `inputs` → `history` → `forecasts` → `planning` → `output`; `explain` (the *Why*) is used by all. See `CLAUDE.md` for a detailed map of the code.

- Adding a device or price source: [Drivers](drivers.md).
- Adding a planner, consumption forecaster, tariff or PV forecast source: [Modules](modules.md) — as an own module in `/config`, or as a built-in one in the module's package (add it to `BUILTIN` in its `__init__.py`).

Every user-facing text is in English and Dutch (`strings.json`, `translations/en.json`, `translations/nl.json`; the explanations in `explain/messages.py` and `explain/plan_story.py`).
