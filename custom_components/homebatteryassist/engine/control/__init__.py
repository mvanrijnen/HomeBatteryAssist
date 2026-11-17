"""Control layer — BUILT, NOT ACTIVE (HomeBatteryAssist is read-only).

``battery_controller.py``: the safety rules every future control must follow
(master switch off by default, always release, watchdog, refresh, throttle,
idle = release where needed, limits). Nothing in HomeBatteryAssist creates or
enables a controller. ``control_loop.py``: the control loop, written out as
comment only. ``interceptors/``: the interceptor modules (the user's last say
per battery before a command), used by the virtual batteries now.
"""
