"""History: recorded data used as the basis for forecasting.

- ``consumption``: house consumption, time-weighted average per interval
"""

from .consumption_history import ConsumptionHistory, ConsumptionRecord

__all__ = ["ConsumptionHistory", "ConsumptionRecord"]
