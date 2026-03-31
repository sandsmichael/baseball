"""
Simple in-memory TTL cache for expensive Yahoo API calls.
"""
import time
import threading
from typing import Any


class TTLCache:
    def __init__(self):
        self._store: dict[str, tuple[Any, float]] = {}
        self._lock = threading.Lock()

    def get(self, key: str, ttl: int) -> Any | None:
        """Return cached value if present and not older than ttl seconds, else None."""
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            value, ts = entry
            if (time.time() - ts) > ttl:
                del self._store[key]
                return None
            return value

    def set(self, key: str, value: Any) -> None:
        with self._lock:
            self._store[key] = (value, time.time())

    def invalidate(self, *keys: str) -> None:
        with self._lock:
            for k in keys:
                self._store.pop(k, None)

    def invalidate_prefix(self, prefix: str) -> None:
        with self._lock:
            to_del = [k for k in self._store if k.startswith(prefix)]
            for k in to_del:
                del self._store[k]

    def age(self, key: str) -> float | None:
        """Return seconds since the key was cached, or None if not cached."""
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            return time.time() - entry[1]


# TTL constants (seconds)
TTL_LEAGUES = 600       # 10 min
TTL_ROSTER = 60         # 1 min
TTL_MATCHUP = 300       # 5 min
TTL_STANDINGS = 300     # 5 min
TTL_WAIVERS = 120       # 2 min
TTL_ALL_ROSTERS = 120   # 2 min
TTL_IL = 120            # 2 min
TTL_DTD = 120           # 2 min
TTL_TOP_AVAIL = 300     # 5 min
TTL_TOP_STATS = 600     # 10 min
TTL_UPGRADES = 600      # 10 min
TTL_ADP = 600           # 10 min
TTL_MATCHUP_SCORES = 300  # 5 min


cache = TTLCache()
