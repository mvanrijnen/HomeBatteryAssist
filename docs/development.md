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

All backend logic is in `engine/`, in layers: see [Architecture](architecture.md) for the layers and the folder map; `CLAUDE.md` has a detailed map of the code.

- Connecting a device (battery model or reader, meter): [Drivers](drivers.md).
- Adding a planner, consumption forecaster, price source, tariff or PV forecast source: [Modules](modules.md) — as an own module in `/config`, or as a built-in one in its layer (add it to `BUILTIN` / `DRIVERS` in its `__init__.py`).

Every user-facing text is in English and Dutch (`strings.json`, `translations/en.json`, `translations/nl.json`; the explanations in `engine/explain/messages.py` and `engine/explain/plan_story.py`).
