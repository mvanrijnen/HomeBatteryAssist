"""Number platform; the entities live in ``output.numbers``."""

from .output.numbers import async_setup_entry as _async_setup_entry
from .output.registry_cleanup import completing

async_setup_entry = completing(_async_setup_entry, "number")

__all__ = ["async_setup_entry"]
