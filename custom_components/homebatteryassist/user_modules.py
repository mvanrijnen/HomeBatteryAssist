"""Loading the user's own modules from ``/config/homebatteryassist/<kind>/``.

Every kind of module (planners, consumption forecasters, tariffs, PV forecast
sources) has a base class with a ``key``. Own modules are Python files in the
kind's folder; every subclass of the base class defined in such a file (with
a ``key``) is loaded and keyed ``custom_<key>``. A file that fails to load is
skipped and logged. Files whose name starts with ``_`` are ignored.

Loading runs in the executor (it imports files). Own modules are code that
runs inside Home Assistant: only use files you trust.
"""

from __future__ import annotations

import importlib.util
import inspect
import logging
import sys
from pathlib import Path
from typing import Any

from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

CUSTOM_PREFIX = "custom_"
ROOT_FOLDER = "homebatteryassist"


def load_modules_from[T](folder: Path, base: type[T], kind: str) -> dict[str, T]:
    """Instances of the ``base`` subclasses defined in ``folder``'s files (blocking)."""
    found: dict[str, T] = {}
    if not folder.is_dir():
        return found
    for path in sorted(folder.glob("*.py")):
        if path.name.startswith("_"):
            continue
        name = f"homebatteryassist_{kind}_{path.stem}"
        try:
            spec = importlib.util.spec_from_file_location(name, path)
            if spec is None or spec.loader is None:
                continue
            module = importlib.util.module_from_spec(spec)
            sys.modules[name] = module
            spec.loader.exec_module(module)
        except Exception:
            _LOGGER.exception("%s file %s could not be loaded", kind, path)
            continue
        for _, cls in inspect.getmembers(module, inspect.isclass):
            if not (
                issubclass(cls, base)
                and cls is not base
                and cls.__module__ == name
                and getattr(cls, "key", "")
            ):
                continue
            key = f"{CUSTOM_PREFIX}{cls.key}"
            if key in found:
                _LOGGER.warning("%s key %s defined twice; %s skipped", kind, key, path)
                continue
            try:
                found[key] = cls()
            except Exception:
                _LOGGER.exception("%s %s in %s could not be created", kind, cls, path)
    return found


async def async_load_modules[T](
    hass: HomeAssistant, kind: str, base: type[T]
) -> dict[str, T]:
    """The user's own modules of ``kind`` from ``/config/homebatteryassist/<kind>``."""
    folder = Path(hass.config.path(ROOT_FOLDER, kind))
    found = await hass.async_add_executor_job(load_modules_from, folder, base, kind)
    if found:
        _LOGGER.info("Own %s loaded: %s", kind, ", ".join(found))
    return found


def module_name(module: Any, key: str) -> str:
    """The name of a module for the user."""
    return getattr(module, "name", "") or key
