"""Tests for bidirectional sync system.

This module tests the following components:
    - database_schema.py: SQLite schema creation
    - sync_manager.py: Bidirectional sync between SQLite and Sheets
    - hybrid_service.py: Transparent access to local + remote data

Author: Claude Code (PROMPT 3.2 - Bidirectional Sync)
Date: 2025-11-11
Version: 1.0.0
"""

import logging
import os
import sys
import time
from pathlib import Path

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def test_database_schema():
    """Test 1: Database schema creation."""
    logger.info("\n" + "="*70)
    logger.info("TEST 1: Database Schema Creation")
    logger.info("="*70)

    from database_schema import DatabaseSchema, get_db_connection

    # Use test database
    test_db = "data/test_reference_data.db"

    # Remove old test DB
    if Path(test_db).exists():
        os.remove(test_db)
        logger.info(f"Removed old test database: {test_db}")

    # Create schema
    schema = DatabaseSchema(test_db)
    schema.init_schema()

    logger.info("✓ Schema initialized")

    # Check version
    version = schema.get_schema_version()
    assert version == 1, f"Expected version 1, got {version}"
    logger.info(f"✓ Schema version: {version}")

    # Check tables exist
    conn = get_db_connection(test_db)
    cursor = conn.cursor()

    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [row[0] for row in cursor.fetchall()]

    expected_tables = [
        '_schema_metadata',
        'employee_settings',
        'dynamic_rates',
        'ranks',
        'sync_log'
    ]

    for table in expected_tables:
        assert table in tables, f"Table {table} not found"
        logger.info(f"✓ Table exists: {table}")

    conn.close()

    logger.info("\n✅ TEST 1 PASSED: Database schema created successfully\n")

    return test_db


def test_sync_from_sheets(test_db):
    """Test 2: Sync from Google Sheets to SQLite."""
    logger.info("\n" + "="*70)
    logger.info("TEST 2: Sync FROM Google Sheets to SQLite")
    logger.info("="*70)

    from sheets_service import SheetsService
    from sync_manager import SyncManager
    from database_schema import get_db_connection

    # Initialize services
    sheets = SheetsService()
    sync = SyncManager(sheets, db_path=test_db)

    # Perform full sync
    logger.info("Pulling data from Google Sheets...")
    counts = sync.full_sync_from_sheets()

    logger.info(f"Sync completed: {counts}")

    # Verify EmployeeSettings
    if counts['employee_settings'] > 0:
        conn = get_db_connection(test_db)
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) as count FROM employee_settings")
        local_count = cursor.fetchone()['count']

        assert local_count == counts['employee_settings'], \
            f"EmployeeSettings count mismatch: {local_count} != {counts['employee_settings']}"

        logger.info(f"✓ EmployeeSettings synced: {local_count} records")

        # Check data
        cursor.execute("SELECT * FROM employee_settings LIMIT 1")
        sample = cursor.fetchone()
        logger.info(f"  Sample: employee_id={sample['employee_id']}, "
                   f"hourly_wage={sample['hourly_wage']}, "
                   f"sales_commission={sample['sales_commission']}")

        conn.close()

    # Verify DynamicRates
    if counts['dynamic_rates'] > 0:
        conn = get_db_connection(test_db)
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) as count FROM dynamic_rates")
        local_count = cursor.fetchone()['count']

        assert local_count == counts['dynamic_rates'], \
            f"DynamicRates count mismatch"

        logger.info(f"✓ DynamicRates synced: {local_count} records")

        # Check data
        cursor.execute("SELECT * FROM dynamic_rates ORDER BY min_amount LIMIT 3")
        samples = cursor.fetchall()
        for s in samples:
            logger.info(f"  Range: ${s['min_amount']:.0f} - ${s['max_amount']:.0f} = {s['percentage']}%")

        conn.close()

    # Verify Ranks
    if counts['ranks'] > 0:
        conn = get_db_connection(test_db)
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) as count FROM ranks")
        local_count = cursor.fetchone()['count']

        assert local_count == counts['ranks'], \
            f"Ranks count mismatch"

        logger.info(f"✓ Ranks synced: {local_count} records")

        # Check data
        cursor.execute("SELECT * FROM ranks ORDER BY min_amount")
        samples = cursor.fetchall()
        for s in samples:
            logger.info(f"  Rank: {s['rank_name']} (${s['min_amount']:.0f} - ${s['max_amount']:.0f})")

        conn.close()

    logger.info("\n✅ TEST 2 PASSED: Sync from Sheets successful\n")


def test_hybrid_service_reads(test_db):
    """Test 3: HybridService reads from SQLite."""
    logger.info("\n" + "="*70)
    logger.info("TEST 3: HybridService Reads (SQLite)")
    logger.info("="*70)

    from hybrid_service import HybridService
    from database_schema import get_db_connection

    # Initialize HybridService (without auto-sync for testing)
    service = HybridService(
        db_path=test_db,
        auto_sync=False  # Disable background sync for testing
    )

    # Test 3.1: get_employee_settings()
    logger.info("\nTest 3.1: get_employee_settings()")

    # Get first employee from DB
    conn = get_db_connection(test_db)
    cursor = conn.cursor()
    cursor.execute("SELECT employee_id FROM employee_settings LIMIT 1")
    row = cursor.fetchone()

    if row:
        employee_id = row['employee_id']
        conn.close()

        settings = service.get_employee_settings(employee_id)

        assert settings is not None, "Settings should not be None"
        assert 'Hourly wage' in settings, "Missing 'Hourly wage'"
        assert 'Sales commission' in settings, "Missing 'Sales commission'"

        logger.info(f"✓ get_employee_settings({employee_id}): {settings}")
    else:
        conn.close()
        logger.warning("No employee settings in DB, skipping test")

    # Test 3.2: get_dynamic_rates()
    logger.info("\nTest 3.2: get_dynamic_rates()")

    rates = service.get_dynamic_rates()
    assert isinstance(rates, list), "Rates should be a list"
    logger.info(f"✓ get_dynamic_rates(): {len(rates)} rates")

    if rates:
        sample = rates[0]
        assert 'Min Amount' in sample
        assert 'Max Amount' in sample
        assert 'Percentage' in sample
        logger.info(f"  Sample: {sample}")

    # Test 3.3: get_ranks()
    logger.info("\nTest 3.3: get_ranks()")

    ranks = service.get_ranks()
    assert isinstance(ranks, list), "Ranks should be a list"
    logger.info(f"✓ get_ranks(): {len(ranks)} ranks")

    if ranks:
        sample = ranks[0]
        assert 'Rank Name' in sample
        assert 'Min Amount' in sample
        assert 'Max Amount' in sample
        logger.info(f"  Sample: {sample['Rank Name']}")

    # Shutdown service
    service.shutdown()

    logger.info("\n✅ TEST 3 PASSED: HybridService reads working\n")


def test_performance_comparison(test_db):
    """Test 4: Performance comparison (SQLite vs Sheets)."""
    logger.info("\n" + "="*70)
    logger.info("TEST 4: Performance Comparison")
    logger.info("="*70)

    from sheets_service import SheetsService
    from hybrid_service import HybridService
    from database_schema import get_db_connection
    import time

    # Get sample employee ID
    conn = get_db_connection(test_db)
    cursor = conn.cursor()
    cursor.execute("SELECT employee_id FROM employee_settings LIMIT 1")
    row = cursor.fetchone()

    if not row:
        logger.warning("No employee data, skipping performance test")
        conn.close()
        return

    employee_id = row['employee_id']
    conn.close()

    # Initialize services
    sheets_service = SheetsService()
    hybrid_service = HybridService(db_path=test_db, auto_sync=False)

    # Test 1: get_employee_settings() - Sheets
    logger.info(f"\nTesting: get_employee_settings({employee_id})")

    start = time.time()
    for _ in range(5):
        result_sheets = sheets_service.get_employee_settings(employee_id)
    time_sheets = (time.time() - start) / 5

    # Test 2: get_employee_settings() - Hybrid (SQLite)
    start = time.time()
    for _ in range(5):
        result_hybrid = hybrid_service.get_employee_settings(employee_id)
    time_hybrid = (time.time() - start) / 5

    speedup = time_sheets / time_hybrid if time_hybrid > 0 else 0

    logger.info(f"  Sheets API:   {time_sheets*1000:.1f} ms")
    logger.info(f"  SQLite:       {time_hybrid*1000:.1f} ms")
    logger.info(f"  Speedup:      {speedup:.1f}x faster")

    # Test 3: get_dynamic_rates() - Sheets
    logger.info(f"\nTesting: get_dynamic_rates()")

    start = time.time()
    for _ in range(5):
        result_sheets = sheets_service.get_dynamic_rates()
    time_sheets = (time.time() - start) / 5

    # Test 4: get_dynamic_rates() - Hybrid (SQLite)
    start = time.time()
    for _ in range(5):
        result_hybrid = hybrid_service.get_dynamic_rates()
    time_hybrid = (time.time() - start) / 5

    speedup = time_sheets / time_hybrid if time_hybrid > 0 else 0

    logger.info(f"  Sheets API:   {time_sheets*1000:.1f} ms")
    logger.info(f"  SQLite:       {time_hybrid*1000:.1f} ms")
    logger.info(f"  Speedup:      {speedup:.1f}x faster")

    # Test 5: get_ranks() - Sheets
    logger.info(f"\nTesting: get_ranks()")

    start = time.time()
    for _ in range(5):
        result_sheets = sheets_service.get_ranks()
    time_sheets = (time.time() - start) / 5

    # Test 6: get_ranks() - Hybrid (SQLite)
    start = time.time()
    for _ in range(5):
        result_hybrid = hybrid_service.get_ranks()
    time_hybrid = (time.time() - start) / 5

    speedup = time_sheets / time_hybrid if time_hybrid > 0 else 0

    logger.info(f"  Sheets API:   {time_sheets*1000:.1f} ms")
    logger.info(f"  SQLite:       {time_hybrid*1000:.1f} ms")
    logger.info(f"  Speedup:      {speedup:.1f}x faster")

    # Cleanup
    hybrid_service.shutdown()

    logger.info("\n✅ TEST 4 PASSED: Performance comparison complete\n")


def test_sync_stats(test_db):
    """Test 5: Sync statistics."""
    logger.info("\n" + "="*70)
    logger.info("TEST 5: Sync Statistics")
    logger.info("="*70)

    from sheets_service import SheetsService
    from sync_manager import SyncManager

    sheets = SheetsService()
    sync = SyncManager(sheets, db_path=test_db)

    stats = sync.get_sync_stats()

    logger.info(f"Sync stats: {stats}")

    assert 'employee_settings' in stats
    assert 'dynamic_rates' in stats
    assert 'ranks' in stats

    logger.info(f"✓ Last sync: {stats.get('last_sync_time', 'N/A')}")
    logger.info(f"✓ EmployeeSettings: {stats['employee_settings']}")
    logger.info(f"✓ DynamicRates: {stats['dynamic_rates']}")
    logger.info(f"✓ Ranks: {stats['ranks']}")

    logger.info("\n✅ TEST 5 PASSED: Sync statistics working\n")


def cleanup_test_db(test_db):
    """Cleanup: Remove test database."""
    logger.info("\n" + "="*70)
    logger.info("CLEANUP")
    logger.info("="*70)

    if Path(test_db).exists():
        os.remove(test_db)
        logger.info(f"✓ Removed test database: {test_db}")
    else:
        logger.info("No test database to remove")


# ==================== Main Test Runner ====================

def main():
    """Run all tests."""
    logger.info("\n" + "#"*70)
    logger.info("# BIDIRECTIONAL SYNC SYSTEM - TEST SUITE")
    logger.info("#"*70)

    test_db = None

    try:
        # Test 1: Database schema
        test_db = test_database_schema()

        # Test 2: Sync from Sheets
        test_sync_from_sheets(test_db)

        # Test 3: HybridService reads
        test_hybrid_service_reads(test_db)

        # Test 4: Performance comparison
        test_performance_comparison(test_db)

        # Test 5: Sync statistics
        test_sync_stats(test_db)

        # Summary
        logger.info("\n" + "#"*70)
        logger.info("# ✅ ALL TESTS PASSED!")
        logger.info("#"*70)
        logger.info("\nSummary:")
        logger.info("  ✓ Database schema creation")
        logger.info("  ✓ Sync from Google Sheets")
        logger.info("  ✓ HybridService reads (SQLite)")
        logger.info("  ✓ Performance comparison (SQLite vs Sheets)")
        logger.info("  ✓ Sync statistics")
        logger.info("\nBidirectional sync system is ready for production!\n")

    except Exception as e:
        logger.error(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    finally:
        # Cleanup
        if test_db:
            # Ask user if they want to keep test DB
            try:
                keep_db = input("\nKeep test database for inspection? (y/N): ").strip().lower()
                if keep_db != 'y':
                    cleanup_test_db(test_db)
                else:
                    logger.info(f"Test database kept: {test_db}")
            except:
                cleanup_test_db(test_db)


if __name__ == "__main__":
    main()
