#!/usr/bin/env python3
"""Test script for cache manager functionality.

Tests:
1. Basic cache operations (get, set, invalidate)
2. TTL expiration
3. Cache statistics
4. Integration with SheetsService

Author: Claude Code (PROMPT 2.2 - Local Caching System)
Date: 2025-11-10
"""

import logging
import time
from services import sheets_service, cache_manager

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def test_basic_cache():
    """Test basic cache operations."""
    logger.info("=" * 70)
    logger.info("TEST 1: Basic Cache Operations")
    logger.info("=" * 70)

    # Clear cache
    cache_manager.clear()

    # Test set and get
    cache_manager.set("test", "key1", "value1", ttl=60)
    result = cache_manager.get("test", "key1")
    assert result == "value1", f"Expected 'value1', got {result}"
    logger.info("✓ SET and GET work correctly")

    # Test cache hit
    result2 = cache_manager.get("test", "key1")
    assert result2 == "value1", f"Expected 'value1', got {result2}"
    logger.info("✓ Cache HIT works correctly")

    # Test cache miss
    result3 = cache_manager.get("test", "nonexistent")
    assert result3 is None, f"Expected None, got {result3}"
    logger.info("✓ Cache MISS works correctly")

    # Test invalidation
    cache_manager.invalidate_key("test", "key1")
    result4 = cache_manager.get("test", "key1")
    assert result4 is None, f"Expected None after invalidation, got {result4}"
    logger.info("✓ Cache INVALIDATION works correctly")

    logger.info("")


def test_ttl_expiration():
    """Test TTL expiration."""
    logger.info("=" * 70)
    logger.info("TEST 2: TTL Expiration")
    logger.info("=" * 70)

    # Clear cache
    cache_manager.clear()

    # Set value with 2 second TTL
    cache_manager.set("test", "expiring_key", "will_expire", ttl=2)
    logger.info("Set key with 2 second TTL")

    # Get immediately (should work)
    result1 = cache_manager.get("test", "expiring_key")
    assert result1 == "will_expire", f"Expected 'will_expire', got {result1}"
    logger.info("✓ Key accessible immediately after set")

    # Wait 3 seconds
    logger.info("Waiting 3 seconds for TTL expiration...")
    time.sleep(3)

    # Get after expiration (should return None)
    result2 = cache_manager.get("test", "expiring_key")
    assert result2 is None, f"Expected None after expiration, got {result2}"
    logger.info("✓ Key expired correctly after TTL")

    logger.info("")


def test_cache_stats():
    """Test cache statistics."""
    logger.info("=" * 70)
    logger.info("TEST 3: Cache Statistics")
    logger.info("=" * 70)

    # Clear cache and stats
    cache_manager.clear()
    cache_manager._stats = {"hits": 0, "misses": 0, "sets": 0, "invalidations": 0}

    # Perform operations
    cache_manager.set("test", "k1", "v1", ttl=60)
    cache_manager.set("test", "k2", "v2", ttl=60)
    cache_manager.get("test", "k1")  # hit
    cache_manager.get("test", "k1")  # hit
    cache_manager.get("test", "nonexistent")  # miss
    cache_manager.invalidate_key("test", "k2")

    # Check stats
    stats = cache_manager.get_stats()
    logger.info(f"Cache Stats: {stats}")

    assert stats["sets"] == 2, f"Expected 2 sets, got {stats['sets']}"
    assert stats["hits"] == 2, f"Expected 2 hits, got {stats['hits']}"
    assert stats["misses"] == 1, f"Expected 1 miss, got {stats['misses']}"
    assert stats["invalidations"] == 1, f"Expected 1 invalidation, got {stats['invalidations']}"

    logger.info("✓ Cache statistics are correct")
    logger.info("")


def test_sheets_integration():
    """Test integration with SheetsService."""
    logger.info("=" * 70)
    logger.info("TEST 4: Integration with SheetsService")
    logger.info("=" * 70)

    # Clear cache
    cache_manager.clear()
    cache_manager._stats = {"hits": 0, "misses": 0, "sets": 0, "invalidations": 0}

    # Test get_dynamic_rates (should cache)
    logger.info("Calling get_dynamic_rates() first time (should MISS)...")
    rates1 = sheets_service.get_dynamic_rates()
    logger.info(f"Got {len(rates1)} dynamic rates")

    stats1 = cache_manager.get_stats()
    logger.info(f"Stats after first call: hits={stats1['hits']}, misses={stats1['misses']}")

    # Call again (should hit cache)
    logger.info("Calling get_dynamic_rates() second time (should HIT)...")
    rates2 = sheets_service.get_dynamic_rates()
    logger.info(f"Got {len(rates2)} dynamic rates")

    stats2 = cache_manager.get_stats()
    logger.info(f"Stats after second call: hits={stats2['hits']}, misses={stats2['misses']}")

    # Verify cache hit
    assert stats2["hits"] > stats1["hits"], "Expected cache hit on second call"
    logger.info("✓ SheetsService caching works correctly")

    # Test get_ranks
    logger.info("Calling get_ranks() first time (should MISS)...")
    ranks1 = sheets_service.get_ranks()
    logger.info(f"Got {len(ranks1)} ranks")

    logger.info("Calling get_ranks() second time (should HIT)...")
    ranks2 = sheets_service.get_ranks()
    logger.info(f"Got {len(ranks2)} ranks")

    stats3 = cache_manager.get_stats()
    logger.info(f"Stats after ranks calls: hits={stats3['hits']}, misses={stats3['misses']}")
    logger.info("✓ Multiple methods can use cache")

    logger.info("")


def test_summary():
    """Print final summary."""
    logger.info("=" * 70)
    logger.info("FINAL SUMMARY")
    logger.info("=" * 70)

    stats = cache_manager.get_stats()
    cache_manager.log_stats()

    logger.info("")
    logger.info("✅ All tests PASSED!")
    logger.info("")
    logger.info("Cache is ready for production use.")
    logger.info("")


if __name__ == "__main__":
    try:
        test_basic_cache()
        test_ttl_expiration()
        test_cache_stats()
        test_sheets_integration()
        test_summary()

    except AssertionError as e:
        logger.error(f"❌ TEST FAILED: {e}")
        exit(1)
    except Exception as e:
        logger.error(f"❌ UNEXPECTED ERROR: {e}", exc_info=True)
        exit(1)
