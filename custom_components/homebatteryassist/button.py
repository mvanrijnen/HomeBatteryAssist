"""Button platform; the entities live in ``output.buttons``."""

from .output.buttons import async_setup_entry as _async_setup_entry
from .output.registry_cleanup import completing

async_setup_entry = completing(_async_setup_entry, "button")

__all__ = ["async_setup_entry"]
