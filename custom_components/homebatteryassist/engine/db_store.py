"""Where the big stores live: JSON files (default) or a database.

The consumption history and the forecast accuracy are rewritten whole in
Home Assistant's ``.storage`` (JSON, about 0.7 MB each). With a database
(option ``storage_backend``) they are kept as rows instead: one row per
record / prediction / result, and a save only writes the rows that changed
(on an SD card far less wear). Through SQLAlchemy, which Home Assistant has
on board for its recorder:

- ``sqlite``: an own file ``/config/homebatteryassist/homebatteryassist.db``;
- ``mysql`` (MySQL / MariaDB) and ``postgresql``: a server, by URL
  (``storage_url``), e.g. ``mysql://user:password@core-mariadb/hba?charset=utf8mb4``.

Changing the choice moves the data along: every store remembers where it was
kept last (``homebatteryassist.storage_backend`` in ``.storage``) and, when
that differs, is loaded from there once and written to the new place. A
database that cannot be reached at start: the JSON file is used for this run
(and moved to the database on a later start).

``HbaStore`` has the part of ``helpers.storage.Store`` the stores use:
``async_load``, ``async_save`` and ``async_delay_save``.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from collections.abc import Callable, Mapping
from typing import Any

from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.storage import Store

_LOGGER = logging.getLogger(__name__)

BACKEND_JSON = "json"
BACKEND_SQLITE = "sqlite"
BACKEND_MYSQL = "mysql"
BACKEND_POSTGRESQL = "postgresql"
BACKENDS = (BACKEND_JSON, BACKEND_SQLITE, BACKEND_MYSQL, BACKEND_POSTGRESQL)
# Tested on a real setup (the "(not tested)" labels follow this).
VERIFIED = {
    BACKEND_JSON: True,
    BACKEND_SQLITE: True,
    BACKEND_MYSQL: False,
    BACKEND_POSTGRESQL: False,
}
SERVER_BACKENDS = (BACKEND_MYSQL, BACKEND_POSTGRESQL)
SQLITE_FILE = "homebatteryassist/homebatteryassist.db"
TABLE = "hba_store"
SEP = "|"
JSON = "json"  # marker: kept in the JSON file
MARKER_KEY = "homebatteryassist.storage_backend"

# How a store's data becomes rows: top-level key -> shape. Other keys are one
# row each.
#   "list":     a list of dicts with "start" (one row per item, in order)
#   "map":      a dict (one row per key)
#   "map_list": a dict of lists (one row per item)
#   "map_map":  a dict of dicts (one row per inner key)
type Layout = Mapping[str, str]


def database_url(
    hass: HomeAssistant, backend: str | None, url: str | None
) -> str | None:
    """The SQLAlchemy URL for the chosen backend (None: JSON files)."""
    if backend == BACKEND_SQLITE:
        return f"sqlite:///{hass.config.path(SQLITE_FILE)}"
    if backend in SERVER_BACKENDS and url:
        return url.strip()  # the recorder's URL form works as it is
    return None


def describe(url: str | None) -> str:
    """The backend without user and password (logs, diagnostics)."""
    if not url:
        return BACKEND_JSON
    scheme, _, rest = url.partition("://")
    host = rest.rsplit("@", 1)[-1]
    if scheme.startswith("sqlite"):
        return f"sqlite ({os.path.basename(host)})"
    return f"{scheme} ({host.split('?', 1)[0]})"


def _dumps(value: Any) -> str:
    return json.dumps(value, separators=(",", ":"), ensure_ascii=False)


def split(data: Mapping[str, Any], layout: Layout) -> dict[str, str]:
    """A store's data as rows (key -> JSON text)."""
    rows: dict[str, str] = {}

    def items(prefix: str, values: Any) -> None:
        seen: dict[str, int] = {}
        for item in values or []:
            start = str(item.get("start", "")) if isinstance(item, dict) else ""
            n = seen.get(start, 0)
            seen[start] = n + 1
            rows[f"{prefix}{SEP}{start}{SEP}{n:04d}"] = _dumps(item)

    for top, value in data.items():
        shape = layout.get(top)
        if shape == "list" and isinstance(value, list):
            items(top, value)
        elif shape == "map" and isinstance(value, dict):
            for key, inner in value.items():
                rows[f"{top}{SEP}{key}"] = _dumps(inner)
        elif shape == "map_list" and isinstance(value, dict):
            for kind, values in value.items():
                items(f"{top}{SEP}{kind}", values)
        elif shape == "map_map" and isinstance(value, dict):
            for kind, inner in value.items():
                for key, item in (inner or {}).items():
                    rows[f"{top}{SEP}{kind}{SEP}{key}"] = _dumps(item)
        else:
            rows[top] = _dumps(value)
    return rows


def join(rows: Mapping[str, str], layout: Layout) -> dict[str, Any]:
    """Rows back to a store's data."""
    data: dict[str, Any] = {}
    for key in sorted(rows):
        parts = key.split(SEP)
        top = parts[0]
        shape = layout.get(top)
        value = json.loads(rows[key])
        if shape is None or len(parts) == 1:
            data[top] = value
        elif shape == "list":
            data.setdefault(top, []).append(value)
        elif shape == "map":
            data.setdefault(top, {})[parts[1]] = value
        elif shape == "map_list":
            data.setdefault(top, {}).setdefault(parts[1], []).append(value)
        elif shape == "map_map":
            data.setdefault(top, {}).setdefault(parts[1], {})[SEP.join(parts[2:])] = (
                value
            )
    return data


class _Database:
    """One database (blocking; run in the executor)."""

    def __init__(self, url: str) -> None:
        self.url = url
        self._engine: Any = None
        self._table: Any = None

    def _open(self) -> tuple[Any, Any]:
        if self._engine is None:
            from sqlalchemy import (
                Column,
                MetaData,
                String,
                Table,
                Text,
                create_engine,
            )
            from sqlalchemy.dialects import mysql

            if self.url.startswith("sqlite:///"):
                folder = os.path.dirname(self.url.removeprefix("sqlite:///"))
                if folder:
                    os.makedirs(folder, exist_ok=True)
            metadata = MetaData()
            table = Table(
                TABLE,
                metadata,
                Column("store", String(100), primary_key=True),
                Column("key", String(191), primary_key=True),
                Column("value", Text().with_variant(mysql.LONGTEXT(), "mysql")),
            )
            engine = create_engine(self.url, pool_pre_ping=True)
            metadata.create_all(engine)
            self._engine, self._table = engine, table
        return self._engine, self._table

    def check(self) -> None:
        """Connect once (the settings check)."""
        engine, _table = self._open()
        with engine.connect():
            pass

    def read(self, store: str) -> dict[str, str]:
        from sqlalchemy import select

        engine, table = self._open()
        with engine.connect() as conn:
            result = conn.execute(
                select(table.c.key, table.c.value).where(table.c.store == store)
            )
            return {key: value for key, value in result}

    def write(
        self,
        store: str,
        upserts: Mapping[str, str],
        deletes: set[str],
        replace: bool = False,
    ) -> None:
        from sqlalchemy import delete, insert

        engine, table = self._open()
        with engine.begin() as conn:
            if replace:
                conn.execute(delete(table).where(table.c.store == store))
            else:
                gone = [*deletes, *upserts]
                for i in range(0, len(gone), 500):
                    conn.execute(
                        delete(table).where(
                            table.c.store == store, table.c.key.in_(gone[i : i + 500])
                        )
                    )
            if upserts:
                conn.execute(
                    insert(table),
                    [
                        {"store": store, "key": key, "value": value}
                        for key, value in upserts.items()
                    ],
                )

    def close(self) -> None:
        if self._engine is not None:
            self._engine.dispose()
            self._engine = None


_DATABASES: dict[str, _Database] = {}


def _database(url: str) -> _Database:
    if url not in _DATABASES:
        _DATABASES[url] = _Database(url)
    return _DATABASES[url]


async def async_check_database(hass: HomeAssistant, url: str) -> bool:
    """Whether the database can be reached (and the table made)."""
    database = _Database(url)
    try:
        await hass.async_add_executor_job(database.check)
    except Exception as err:  # any driver error: not reachable
        _LOGGER.warning("Database %s not reachable: %s", describe(url), err)
        return False
    finally:
        await hass.async_add_executor_job(database.close)
    return True


class _Markers:
    """Where each store was kept last (store name -> URL or ``JSON``)."""

    def __init__(self, hass: HomeAssistant) -> None:
        self._store: Store[dict[str, str]] = Store(hass, 1, MARKER_KEY)
        self._data: dict[str, str] | None = None
        self._lock = asyncio.Lock()

    async def get(self, name: str) -> str | None:
        async with self._lock:
            if self._data is None:
                self._data = await self._store.async_load() or {}
            return self._data.get(name)

    async def set(self, name: str, where: str) -> None:
        async with self._lock:
            if self._data is None:
                self._data = await self._store.async_load() or {}
            if self._data.get(name) != where:
                self._data[name] = where
                await self._store.async_save(self._data)


def _markers(hass: HomeAssistant) -> _Markers:
    key = f"{MARKER_KEY}_markers"
    if key not in hass.data:
        hass.data[key] = _Markers(hass)
    return hass.data[key]


class HbaStore:
    """A store in its JSON file or in a database (see the module docstring)."""

    def __init__(
        self,
        hass: HomeAssistant,
        json_store: Store[dict[str, Any]],
        layout: Layout,
        url: str | None = None,
    ) -> None:
        """Initialize: ``json_store`` is the store's own JSON file."""
        self.hass = hass
        self._json = json_store
        self._layout = layout
        self.url = url
        self.name = json_store.key
        self._saved: dict[str, str] = {}
        self._lock = asyncio.Lock()
        self._unsub: CALLBACK_TYPE | None = None
        self._pending: Callable[[], dict[str, Any]] | None = None
        self._failing = False

    @property
    def where(self) -> str:
        """Where the store is kept (no password)."""
        return describe(self.url)

    async def async_load(self) -> dict[str, Any] | None:
        """Load; moves the data here when it was kept elsewhere last."""
        markers = _markers(self.hass)
        previous = await markers.get(self.name)
        here = self.url or JSON
        if self.url is not None:
            try:
                if previous == here:
                    rows = await self.hass.async_add_executor_job(
                        _database(self.url).read, self.name
                    )
                    self._saved = rows
                    return join(rows, self._layout) if rows else None
                data = await self._load_from(previous)
                rows = split(data or {}, self._layout)
                await self.hass.async_add_executor_job(
                    _database(self.url).write, self.name, rows, set(), True
                )
                self._saved = rows
            except Exception as err:
                _LOGGER.warning(
                    "%s: database %s not reachable (%s); using the JSON file for now",
                    self.name,
                    self.where,
                    err,
                )
                self.url = None
                data = await self._load_from(previous)
                await markers.set(self.name, JSON)
                return data
            _LOGGER.info("%s moved to %s", self.name, self.where)
            await markers.set(self.name, here)
            return data
        if previous not in (None, JSON):
            data = await self._load_from(previous)
            if data is not None:
                await self._json.async_save(data)
            _LOGGER.info("%s moved back to its JSON file", self.name)
            await markers.set(self.name, JSON)
            return data
        return await self._json.async_load()

    async def _load_from(self, where: str | None) -> dict[str, Any] | None:
        """The data where it was kept last (the JSON file when unknown)."""
        if where in (None, JSON):
            return await self._json.async_load()
        try:
            rows = await self.hass.async_add_executor_job(
                _database(where).read, self.name
            )
        except Exception as err:
            _LOGGER.warning(
                "%s: previous database %s not reachable (%s); using the JSON file",
                self.name,
                describe(where),
                err,
            )
            return await self._json.async_load()
        return join(rows, self._layout) if rows else None

    async def async_save(self, data: dict[str, Any]) -> None:
        """Write now (in the database: only the rows that changed)."""
        if self.url is None:
            await self._json.async_save(data)
            return
        rows = split(data, self._layout)
        async with self._lock:
            upserts = {k: v for k, v in rows.items() if self._saved.get(k) != v}
            deletes = set(self._saved) - set(rows)
            if not upserts and not deletes:
                return
            try:
                await self.hass.async_add_executor_job(
                    _database(self.url).write, self.name, upserts, deletes
                )
            except Exception as err:
                if not self._failing:
                    _LOGGER.warning(
                        "%s: writing to %s failed (%s); tried again on the next save",
                        self.name,
                        self.where,
                        err,
                    )
                self._failing = True
                return
            if self._failing:
                _LOGGER.info("%s: writing to %s works again", self.name, self.where)
            self._failing = False
            self._saved = rows

    @callback
    def async_delay_save(
        self, data_func: Callable[[], dict[str, Any]], delay: float = 0
    ) -> None:
        """Write after ``delay`` seconds (a later call moves it)."""
        if self.url is None:
            self._json.async_delay_save(data_func, delay)
            return
        self._pending = data_func
        if self._unsub is not None:
            self._unsub()

        async def write(_now: Any) -> None:
            self._unsub = None
            func, self._pending = self._pending, None
            if func is not None:
                await self.async_save(func())

        self._unsub = async_call_later(self.hass, delay, write)
