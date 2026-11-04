import math
import threading
import time
from collections import defaultdict, deque

from fastapi import Depends, HTTPException, Request, status

from app.models import ApiKey
from app.security import get_current_key


class SlidingWindowRateLimiter:
    """In-memory sliding-window limiter. Per-process; not shared across workers."""

    def __init__(self, max_requests: int, window_seconds: float) -> None:
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, key: str) -> float:
        """Record a hit. Returns 0 if allowed, else seconds until a slot frees up."""
        now = time.monotonic()
        with self._lock:
            hits = self._hits[key]
            while hits and now - hits[0] >= self.window_seconds:
                hits.popleft()
            if len(hits) >= self.max_requests:
                return self.window_seconds - (now - hits[0])
            hits.append(now)
            return 0.0


def limit_link_creation(request: Request, key: ApiKey = Depends(get_current_key)) -> ApiKey:
    retry_after = request.app.state.rate_limiter.check(str(key.id))
    if retry_after > 0:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Rate limit exceeded for link creation",
            headers={"Retry-After": str(math.ceil(retry_after))},
        )
    return key
