"""Shared rate limiter (SlowAPI).

Keyed by client IP. Disabled in tests via settings.rate_limit_enabled=false so
the suite isn't throttled. Applied to abuse-prone endpoints (auth, run creation,
estimate, and the public webhook).
"""

from __future__ import annotations

from slowapi import Limiter
from slowapi.util import get_remote_address

from app.config import settings

limiter = Limiter(
    key_func=get_remote_address,
    enabled=settings.rate_limit_enabled,
)
