"""Binary sensor platform; the entities live in ``output.binary_sensors``."""

from .output.binary_sensors import async_setup_entry as _async_setup_entry
from .output.registry_cleanup import completing

async_setup_entry = completing(_async_setup_entry, "binary_sensor")

__all__ = ["async_setup_entry"]
