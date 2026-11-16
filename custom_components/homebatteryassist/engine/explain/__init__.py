"""Explain: the decision log, telling the user *why* the system does something.

Separate from technical logging (Python ``logging`` per module, for developers):
the decision log holds short, human-readable explanations in the user's
language, persisted, shown in the "Last decision" sensor and fired as the
``homebatteryassist_decision`` event.
"""

from .decision_log import Decision, DecisionLog

__all__ = ["Decision", "DecisionLog"]
