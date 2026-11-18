"""Interceptor: none — everything goes as HomeBatteryAssist proposes (default)."""

from __future__ import annotations

from .base import InterceptInput, Interceptor, InterceptResult


class PassThrough(Interceptor):
    """Approves every proposal."""

    key = "none"
    verified = True
    name = "None (everything as proposed)"

    def intercept(self, data: InterceptInput) -> InterceptResult:
        """Approve everything."""
        return InterceptResult()
