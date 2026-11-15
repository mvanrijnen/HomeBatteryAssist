"""Forecasts: what HomeBatteryAssist derives about the future.

- ``horizon``:     how far ahead planning is possible
- ``coordinator``: collects the price and PV forecast inputs periodically and
                   determines the planning horizon

Future: consumption forecast based on ``history``.
"""
