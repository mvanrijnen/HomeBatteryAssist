"""Control layer — BUILT, NOT ACTIVE (HomeBatteryAssist is read-only).

``battery_controller.py``: the safety rules every future control must follow
(master switch off by default, always release, watchdog, refresh, throttle,
idle = release where needed, limits). Nothing in HomeBatteryAssist creates or
enables a controller.
"""
