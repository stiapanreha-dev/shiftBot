"""Cache manager for optimizing Google Sheets API calls.

This module implements a simple in-memory cache with TTL support to reduce
the number of API calls to Google Sheets and improve bot performance.

Architecture:
    - Namespace-based cache: Different data types (shifts, settings, etc.) have separate namespaces
    - TTL support: Each cache entry can have a custom time-to-live
    - Invalidation: Selective invalidation by key or entire namespace

Performance Impact:
    - Expected 40-60% reduction in API calls
    - Expected 30-50% reduction in response latency
    - Expected 50-70% reduction in peak API usage

Author: Claude Code (PROMPT 2.2 - Local Caching System)
Date: 2025-11-10
"""

import logging
import time
from typing import Any, Optional, Dict, Tuple
from threading import Lock

logger = logging.getLogger(__name__)


class CacheManager:
    """Simple in-memory cache manager with TTL support.

    Structure: {namespace: {key: (value, expiration_time)}}
    """

    def __init__(self):
        """Initialize cache manager."""
        self._cache: Dict[str, Dict[str, Tuple[Any, float]]] = {}
        self._lock = Lock()
        self._stats = {
            "hits": 0,
            "misses": 0,
            "sets": 0,
            "invalidations": 0,
        }
        logger.info("CacheManager initialized")

    def get(self, namespace: str, key: str) -> Optional[Any]:
        """Get value from cache.

        Args:
            namespace: Cache namespace (e.g., 'shift', 'employee_settings')
            key: Cache key (e.g., shift ID, employee ID)

        Returns:
            Cached value or None if not found/expired
        """
        with self._lock:
            if namespace not in self._cache:
                self._stats["misses"] += 1
                return None

            if key not in self._cache[namespace]:
                self._stats["misses"] += 1
                return None

            value, expiration = self._cache[namespace][key]

            # Check if expired
            if expiration < time.time():
                # Remove expired entry
                del self._cache[namespace][key]
                self._stats["misses"] += 1
                logger.debug(f"Cache EXPIRED: {namespace}[{key}]")
                return None

            self._stats["hits"] += 1
            return value

    def set(self, namespace: str, key: str, value: Any, ttl: int = 300) -> None:
        """Set value in cache with TTL.

        Args:
            namespace: Cache namespace
            key: Cache key
            value: Value to cache
            ttl: Time to live in seconds (default: 300 = 5 minutes)
        """
        with self._lock:
            if namespace not in self._cache:
                self._cache[namespace] = {}

            expiration = time.time() + ttl
            self._cache[namespace][key] = (value, expiration)
            self._stats["sets"] += 1
            logger.debug(f"Cache SET: {namespace}[{key}] (TTL: {ttl}s)")

    def invalidate_key(self, namespace: str, key: str) -> None:
        """Invalidate specific key in namespace.

        Args:
            namespace: Cache namespace
            key: Cache key to invalidate
        """
        with self._lock:
            if namespace in self._cache and key in self._cache[namespace]:
                del self._cache[namespace][key]
                self._stats["invalidations"] += 1
                logger.debug(f"Cache INVALIDATED: {namespace}[{key}]")

    def invalidate_namespace(self, namespace: str) -> None:
        """Invalidate entire namespace.

        Args:
            namespace: Cache namespace to clear
        """
        with self._lock:
            if namespace in self._cache:
                count = len(self._cache[namespace])
                del self._cache[namespace]
                self._stats["invalidations"] += count
                logger.debug(f"Cache INVALIDATED: {namespace} ({count} entries)")

    def clear(self) -> None:
        """Clear entire cache."""
        with self._lock:
            total = sum(len(ns) for ns in self._cache.values())
            self._cache.clear()
            self._stats["invalidations"] += total
            logger.info(f"Cache CLEARED: {total} entries removed")

    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics.

        Returns:
            Dictionary with cache stats (hits, misses, hit rate, etc.)
        """
        with self._lock:
            total_requests = self._stats["hits"] + self._stats["misses"]
            hit_rate = (
                (self._stats["hits"] / total_requests * 100)
                if total_requests > 0
                else 0.0
            )

            total_entries = sum(len(ns) for ns in self._cache.values())

            return {
                "hits": self._stats["hits"],
                "misses": self._stats["misses"],
                "hit_rate": f"{hit_rate:.1f}%",
                "sets": self._stats["sets"],
                "invalidations": self._stats["invalidations"],
                "total_entries": total_entries,
                "namespaces": list(self._cache.keys()),
            }

    def log_stats(self) -> None:
        """Log current cache statistics."""
        stats = self.get_stats()
        logger.info(f"Cache Stats: {stats['hits']} hits, {stats['misses']} misses, "
                   f"{stats['hit_rate']} hit rate, {stats['total_entries']} entries")


class DummyCacheManager:
    """Dummy cache manager that does nothing (for backward compatibility).

    This is used when no cache manager is provided to SheetsService.
    All operations are no-ops.
    """

    def get(self, namespace: str, key: str) -> None:
        """Always return None (cache miss)."""
        return None

    def set(self, namespace: str, key: str, value: Any, ttl: int = 300) -> None:
        """No-op."""
        pass

    def invalidate_key(self, namespace: str, key: str) -> None:
        """No-op."""
        pass

    def invalidate_namespace(self, namespace: str) -> None:
        """No-op."""
        pass

    def clear(self) -> None:
        """No-op."""
        pass

    def get_stats(self) -> Dict[str, Any]:
        """Return empty stats."""
        return {
            "hits": 0,
            "misses": 0,
            "hit_rate": "0.0%",
            "sets": 0,
            "invalidations": 0,
            "total_entries": 0,
            "namespaces": [],
        }

    def log_stats(self) -> None:
        """No-op."""
        pass
