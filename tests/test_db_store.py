"""Storage in JSON files or a database (SQLite in the tests), and moving
the data when the choice changes."""

from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.storage import Store

from custom_components.homebatteryassist.engine.db_store import (
    BACKEND_SQLITE,
    HbaStore,
    database_url,
    describe,
    join,
    same_place,
    split,
)

HISTORY = {"records": "list"}
ACCURACY = {"predictions": "map_map", "results": "map_list"}


def _history(n: int) -> dict[str, Any]:
    return {
        "records": [
            {"start": f"2026-11-20T{h:02d}:00:00+00:00", "minutes": 60, "avg_w": h}
            for h in range(n)
        ],
        "excluded_days": ["2026-11-14"],
    }


def test_rows_round_trip() -> None:
    """Data to rows and back, in order, with doubles kept."""
    history = _history(5)
    history["records"].append(dict(history["records"][-1]))
    assert join(split(history, HISTORY), HISTORY) == history
    accuracy = {
        "predictions": {"pv": {"2026-11-20T10:00:00+00:00": {"end": "x", "0-1": 3}}},
        "results": {"pv": [{"start": "a", "actual": 1.0, "pred": {}}]},
        "settings": {"pv": {"mode": "learned"}},
        "price_per_kwh": True,
    }
    assert join(split(accuracy, ACCURACY), ACCURACY) == accuracy


def test_describe_hides_the_password() -> None:
    """Logs and diagnostics never show the user or password; another password
    is the same database."""
    url = "mysql://hba:secret@core-mariadb/hba?charset=utf8mb4"
    assert describe(url) == "mysql (core-mariadb/hba)"
    assert same_place(url, "mysql://hba:new@core-mariadb/hba")
    assert not same_place(url, "mysql://hba:secret@other/hba")
    assert not same_place(url, None)
    assert "secret" not in describe(url)
    assert describe(None) == "json"


def _url(hass: HomeAssistant, tmp_path: Path) -> str:
    hass.config.config_dir = str(tmp_path)
    url = database_url(hass, BACKEND_SQLITE, None)
    assert url is not None
    return url


async def test_moves_to_sqlite_and_back(hass: HomeAssistant, tmp_path: Path) -> None:
    """JSON -> SQLite (moved at load), only changed rows written, and back to
    JSON with what was added in the database."""
    url = _url(hass, tmp_path)
    json_store: Store = Store(hass, 1, "homebatteryassist.test.consumption")
    await json_store.async_save(_history(3))

    store = HbaStore(hass, json_store, HISTORY, url)
    assert await store.async_load() == _history(3)
    assert store.where == "sqlite (homebatteryassist.db)"
    await store.async_save(_history(4))
    assert len(store._saved) == 5  # 4 records + excluded_days

    again = HbaStore(hass, json_store, HISTORY, url)
    assert await again.async_load() == _history(4)

    back = HbaStore(hass, json_store, HISTORY, None)
    assert await back.async_load() == _history(4)
    assert await json_store.async_load() == _history(4)


async def test_delay_save_and_deletes(hass: HomeAssistant, tmp_path: Path) -> None:
    """A delayed save writes; pruned records are deleted from the database."""
    url = _url(hass, tmp_path)
    json_store: Store = Store(hass, 1, "homebatteryassist.test2.consumption")
    store = HbaStore(hass, json_store, HISTORY, url)
    assert await store.async_load() is None
    store.async_delay_save(lambda: _history(6), 0)
    await hass.async_block_till_done()
    await store.async_save({"records": _history(6)["records"][2:]})
    fresh = HbaStore(hass, json_store, HISTORY, url)
    loaded = await fresh.async_load()
    assert [r["avg_w"] for r in loaded["records"]] == [2, 3, 4, 5]
    assert "excluded_days" not in loaded


async def test_unreachable_database_waits(hass: HomeAssistant) -> None:
    """A database that cannot be reached at start: the setup waits and tries
    again (never a stale JSON copy in its place)."""
    json_store: Store = Store(hass, 1, "homebatteryassist.test3.consumption")
    await json_store.async_save(_history(2))
    store = HbaStore(hass, json_store, HISTORY, "sqlite:////nonexistent/dir/x/y.db")
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr("os.makedirs", _fail)
        with pytest.raises(ConfigEntryNotReady):
            await store.async_load()


async def test_failed_write_keeps_everything_in_json(
    hass: HomeAssistant, tmp_path: Path
) -> None:
    """A write that fails while running: all data to the JSON file, which
    moves into the database again at the next start."""
    url = _url(hass, tmp_path)
    json_store: Store = Store(hass, 1, "homebatteryassist.test4.consumption")
    store = HbaStore(hass, json_store, HISTORY, url)
    await store.async_load()
    await store.async_save(_history(2))
    with patch(
        "custom_components.homebatteryassist.engine.db_store._Database.write",
        side_effect=OSError("disk full"),
    ):
        await store.async_save(_history(5))
    assert store.url is None
    assert await json_store.async_load() == _history(5)
    again = HbaStore(hass, json_store, HISTORY, url)
    assert await again.async_load() == _history(5)
    assert same_place(url, url.replace("sqlite:///", "sqlite:///"))


def _fail(*_args: Any, **_kwargs: Any) -> None:
    raise OSError("read-only")
