# Ontwikkeling {#development}

```bash
python -m venv .venv
.venv/bin/pip install -r requirements_test.txt   # Windows: .venv\Scripts\pip
pytest
ruff check . && ruff format --check .
```

De testomgeving van Home Assistant draait niet op native Windows; gebruik daar WSL.

CI (`.github/workflows/validate.yml`) draait hassfest, de HACS-validatie, ruff en pytest.

## Waar alles staat {#where-things-are}

Alle backendlogica staat in `engine/`, in lagen: zie [Architectuur](architecture.md) voor de lagen en het mappenoverzicht; `CLAUDE.md` bevat een gedetailleerd overzicht van de code.

- Een apparaat koppelen (batterijmodel of lezer, meter): [Drivers](drivers.md).
- Een planner, verbruiksvoorspeller, prijsbron, tarief of PV-voorspellingsbron toevoegen: [Modules](modules.md) — als eigen module in `/config`, of als ingebouwde module in zijn laag (voeg hem toe aan `BUILTIN` / `DRIVERS` in zijn `__init__.py`).

Elke tekst die de gebruiker ziet is er in het Engels en het Nederlands (`strings.json`, `translations/en.json`, `translations/nl.json`; de uitleg in `engine/explain/messages.py` en `engine/explain/plan_story.py`).
