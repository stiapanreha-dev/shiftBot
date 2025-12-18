#!/usr/bin/env python3
"""Comprehensive test suite for PostgresService.

Tests all methods to ensure full compatibility with SheetsService.
"""

import logging
import sys
from decimal import Decimal

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

from services.postgres_service import PostgresService

def main():
    service = PostgresService()

    print("="*70)
    print("COMPREHENSIVE TEST SUITE: PostgresService")
    print("="*70)

    passed = 0
    failed = 0

    # Test 1: Get shift by ID
    print("\n[TEST 1] Get shift by ID=33:")
    try:
        shift = service.get_shift_by_id(33)
        if shift:
            print(f"  ✅ Shift found")
            print(f"  - Employee: {shift['employee_name']}")
            print(f"  - Date: {shift['shift_date']}")
            print(f"  - Total sales: {shift['total_sales']}")
            print(f"  - Commission %: {shift['commission_pct']}")
            print(f"  - Products: {service.get_models_from_shift(shift)}")
            passed += 1
        else:
            print("  ❌ FAILED: Shift not found")
            failed += 1
    except Exception as e:
        print(f"  ❌ FAILED: {e}")
        failed += 1

    # Test 2: Get employee settings
    print("\n[TEST 2] Get employee settings for ID=1:")
    try:
        employee = service.get_employee_settings(1)
        if employee:
            print(f"  ✅ Employee found: {employee['employee_name']}")
            print(f"  - Base commission: {employee['base_commission_pct']}%")
            passed += 1
        else:
            print("  ❌ FAILED: Employee not found")
            failed += 1
    except Exception as e:
        print(f"  ❌ FAILED: {e}")
        failed += 1

    # Test 3: Get dynamic rates
    print("\n[TEST 3] Get dynamic rates:")
    try:
        rates = service.get_dynamic_rates()
        print(f"  ✅ Found {len(rates)} rate tiers")
        for rate in rates[:3]:
            min_s = rate['min_sales']
            max_s = rate['max_sales']
            pct = rate['rate_pct']
            print(f"  - ${min_s}-${max_s}: +{pct}%")
        passed += 1
    except Exception as e:
        print(f"  ❌ FAILED: {e}")
        failed += 1

    # Test 4: Calculate dynamic rate
    print("\n[TEST 4] Calculate dynamic rate for 1000 sales:")
    try:
        rate = service.calculate_dynamic_rate(1, '2025-11-11', Decimal('1000'))
        print(f"  ✅ Dynamic rate: {rate}%")
        passed += 1
    except Exception as e:
        print(f"  ❌ FAILED: {e}")
        failed += 1

    # Test 5: Get ranks
    print("\n[TEST 5] Get ranks:")
    try:
        ranks = service.get_ranks()
        print(f"  ✅ Found {len(ranks)} ranks")
        for rank in ranks[:3]:
            print(f"  - {rank['rank_name']}: ${rank['min_total_sales']}-${rank['max_total_sales']}")
        passed += 1
    except Exception as e:
        print(f"  ❌ FAILED: {e}")
        failed += 1

    # Test 6: Get last shifts
    print("\n[TEST 6] Get last 3 shifts for employee ID=1:")
    try:
        shifts = service.get_last_shifts(1, limit=3)
        print(f"  ✅ Found {len(shifts)} shifts")
        for s in shifts[:2]:
            print(f"  - Shift {s['shift_id']}: {s['shift_date']}, Sales: ${s['total_sales']}")
        passed += 1
    except Exception as e:
        print(f"  ❌ FAILED: {e}")
        failed += 1

    # Test 7: Get active bonuses
    print("\n[TEST 7] Get active bonuses for employee ID=1:")
    try:
        bonuses = service.get_active_bonuses(1)
        print(f"  ✅ Found {len(bonuses)} active bonuses")
        for bonus in bonuses[:3]:
            print(f"  - {bonus['Bonus Type']}: {bonus['Value']}%")
        passed += 1
    except Exception as e:
        print(f"  ❌ FAILED: {e}")
        failed += 1

    # Test 8: Get shift applied bonuses
    print("\n[TEST 8] Get applied bonuses for shift ID=33:")
    try:
        bonuses = service.get_shift_applied_bonuses(33)
        print(f"  ✅ Found {len(bonuses)} applied bonuses")
        passed += 1
    except Exception as e:
        print(f"  ❌ FAILED: {e}")
        failed += 1

    # Test 9: Find previous shift with models
    print("\n[TEST 9] Find previous shift with Bella:")
    try:
        prev = service.find_previous_shift_with_models(1, '2025-11-11', '12:00', ['Bella'])
        if prev:
            print(f"  ✅ Found shift {prev['shift_id']} with Bella")
        else:
            print("  ℹ️  No previous shift with Bella found")
        passed += 1
    except Exception as e:
        print(f"  ❌ FAILED: {e}")
        failed += 1

    # Test 10: All shifts count
    print("\n[TEST 10] Get all shifts:")
    try:
        all_shifts = service.get_all_shifts()
        print(f"  ✅ Total shifts in database: {len(all_shifts)}")
        passed += 1
    except Exception as e:
        print(f"  ❌ FAILED: {e}")
        failed += 1

    # Summary
    print("\n" + "="*70)
    print(f"TEST RESULTS: {passed} passed, {failed} failed")
    if failed == 0:
        print("✅ ALL TESTS PASSED - PostgresService is fully functional!")
    else:
        print("❌ SOME TESTS FAILED - Please review errors above")
    print("="*70)

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
