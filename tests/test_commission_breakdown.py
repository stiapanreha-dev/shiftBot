#!/usr/bin/env python3
"""Test script for commission breakdown functionality."""

import sys
from src.handlers import get_commission_breakdown

def test_commission_breakdown():
    """Test the commission breakdown function."""

    print("Testing commission breakdown function...")
    print("-" * 60)

    # Test case 1: No bonus (base + dynamic only)
    print("\nTest 1: Base commission (8%) + Dynamic (7%)")
    employee_id = 1  # Example employee ID
    commission_pct = 15.0
    result = get_commission_breakdown(employee_id, commission_pct, shift_id=None)
    print(f"Result: {result}")
    print(f"Expected format: 15.00% (8.0% base + 7.0% dynamic)")

    # Test case 2: With bonus
    print("\nTest 2: Base (8%) + Dynamic (6%) + Bonus (1%)")
    commission_pct = 15.0
    # Note: To test with actual bonus, we would need a real shift_id with applied bonuses
    # For now, we just test the formatting
    result = get_commission_breakdown(employee_id, commission_pct, shift_id=None)
    print(f"Result: {result}")

    # Test case 3: Only base commission (no dynamic)
    print("\nTest 3: Base commission only (8%)")
    commission_pct = 8.0
    result = get_commission_breakdown(employee_id, commission_pct, shift_id=None)
    print(f"Result: {result}")
    print(f"Expected format: 8.00% (8.0% base)")

    # Test case 4: Negative dynamic (below base)
    print("\nTest 4: Below base commission (7%)")
    commission_pct = 7.0
    result = get_commission_breakdown(employee_id, commission_pct, shift_id=None)
    print(f"Result: {result}")
    print(f"Expected format: 7.00% (8.0% base + -1.0% dynamic)")

    print("\n" + "=" * 60)
    print("Note: To test with actual bonuses, you need a real shift_id")
    print("with percent_next bonuses applied in the ActiveBonuses sheet.")
    print("=" * 60)

if __name__ == "__main__":
    try:
        test_commission_breakdown()
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
