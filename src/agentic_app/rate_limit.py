from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Dict


@dataclass
class RateLimit:
    max_calls: int
    window_seconds: int


class InMemoryRateLimiter:
    def __init__(self) -> None:
        # key = "{session_id}:{tool_name}" -> list[timestamps]
        self._calls: Dict[str, list[float]] = {}

    def allow(self, session_id: str, tool_name: str, rule: RateLimit) -> bool:
        key = f"{session_id}:{tool_name}"
        now = time.time()
        calls = self._calls.get(key, [])
        cutoff = now - rule.window_seconds
        calls = [t for t in calls if t >= cutoff]
        if len(calls) >= rule.max_calls:
            self._calls[key] = calls
            return False
        calls.append(now)
        self._calls[key] = calls
        return True
