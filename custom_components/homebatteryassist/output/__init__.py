"""Output: what HomeBatteryAssist exposes to Home Assistant.

- ``sensors``: sensor entities (house consumption, planning horizon, last decision)

The platform modules in the package root (``sensor.py``, ...) only delegate to
this package, because Home Assistant looks for platforms there. Output is
information only: HomeBatteryAssist never controls devices.
"""
