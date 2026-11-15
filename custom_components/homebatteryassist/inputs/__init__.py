"""Inputs: everything HomeBatteryAssist reads from outside.

- ``units``:        conversion of sensor states to physical values
- ``measurements``: live grid / PV / excluded-load measurements -> house consumption
- ``prices``:       price forecast read from a sensor of another integration
- ``solar``:        PV forecast read from Energy dashboard solar forecast platforms

Inputs only read and normalise data; they do not make forecasts or decisions.
"""
