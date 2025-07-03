"""Tiny in-memory cache with optional TTL eviction."""
import asyncio
import time
from collections import defaultdict
from typing import Any, Dict, Optional


class InMemoryStore:
    def __init__(self, ttl: int | None = 300):
        self._data: Dict[str, Any] = {}
        self._expires: Dict[str, float] = defaultdict(lambda: float("inf"))
        self._ttl = ttl
        self._lock = asyncio.Lock()

    async def save(self, key: str, value: Any) -> None:
        async with self._lock:
            self._data[key] = value
            if self._ttl:
                self._expires[key] = time.time() + self._ttl

    async def get(self, key: str) -> Optional[Any]:
        async with self._lock:
            if key in self._data and time.time() < self._expires[key]:
                return self._data[key]
            return None

    async def update(self, key: str, **kwargs) -> None:
        async with self._lock:
            if key in self._data:
                self._data[key].update(kwargs)


store = InMemoryStore()
