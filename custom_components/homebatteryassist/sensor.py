"""Sensor platform; the entities live in ``output.sensors``."""

from .output.registry_cleanup import completing
from .output.sensors import async_setup_entry as _async_setup_entry

async_setup_entry = completing(_async_setup_entry, "sensor")

__all__ = ["async_setup_entry"]
