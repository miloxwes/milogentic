from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Dict


@dataclass
class RateLimit:
    max_calls: int
    window_seconds: int


@dataclass
class RateLimitDecision:
    allowed: bool
    retry_after_seconds: int = 0


class InMemoryRateLimiter:
    def __init__(self) -> None:
        # key = "{session_id}:{tool_name}" -> list[timestamps]
        self._calls: Dict[str, list[float]] = {}

    def allow(self, session_id: str, tool_name: str, rule: RateLimit) -> RateLimitDecision:
        key = f"{session_id}:{tool_name}"
        now = time.time()
        calls = self._calls.get(key, [])
        cutoff = now - rule.window_seconds
        calls = [t for t in calls if t >= cutoff]
        if len(calls) >= rule.max_calls:
            self._calls[key] = calls
            oldest_call = min(calls)
            retry_after = max(1, int((oldest_call + rule.window_seconds) - now))
            return RateLimitDecision(allowed=False, retry_after_seconds=retry_after)
        calls.append(now)
        self._calls[key] = calls
        return RateLimitDecision(allowed=True)
