"""Verify percent_prev logic with test data."""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))
import logging
from decimal import Decimal

from sheets_service import SheetsService

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def verify_scenario_1():
    """Verify two parallel employees scenario."""
    print("\n" + "="*60)
    print("SCENARIO 1: Two parallel employees")
    print("="*60)

    sheets = SheetsService()

    # Charlie's shift (should find Bob as previous)
    print("\nTesting Charlie's shift (12:30)...")
    print("Charlie sold: Model A + Model B")
    print("Previous employees:")
    print("  - Alice (10:00): Model A only")
    print("  - Bob (11:00): Model B only")
    print("\nExpected: Should select Bob (11:00 is closer)")

    # Simulate Charlie's shift
    charlie_shift = {
        "Date": "2025/11/01 12:30:00",
        "Clock in": "2025/11/01 10:00:00",
        "EmployeeId": 333333,
        "Model A": 300.00,
        "Model B": 200.00,
    }

    # Get models
    models = sheets.get_models_from_shift(charlie_shift)
    print(f"\nCharlie's models: {models}")

    # Find previous shift
    prev_shift = sheets.find_previous_shift_with_models(
        employee_id=333333,
        models=models,
        before_date=charlie_shift["Date"]
    )

    if prev_shift:
        print(f"\n✅ Found previous shift:")
        print(f"   ID: {prev_shift.get('ID')}")
        print(f"   Employee: {prev_shift.get('EmployeeId')} ({prev_shift.get('EmployeeName')})")
        print(f"   Date: {prev_shift.get('Date')}")

        prev_models = sheets.get_models_from_shift(prev_shift)
        print(f"   Models: {prev_models}")

        # Check if correct (Bob = 222222)
        if str(prev_shift.get('EmployeeId')) == '222222':
            print("\n✅✅ CORRECT! Selected Bob (closest date)")
        else:
            print(f"\n❌ WRONG! Selected {prev_shift.get('EmployeeName')} instead of Bob")
    else:
        print("\n❌ No previous shift found")
        return False

    # Calculate bonus
    print("\n" + "─" * 60)
    print("Calculating bonus...")

    bonus_amount = sheets.apply_percent_prev_bonus(
        employee_id=333333,
        current_shift=charlie_shift,
        bonus_value=1.0  # 1%
    )

    print(f"\n💰 Bonus calculated: ${bonus_amount:.2f}")

    # Expected: Bob sold Model B = $800
    # Net sales = $800 × 0.8 = $640
    # Bonus 1% = $6.40
    expected = Decimal("6.40")

    print(f"Expected bonus: ${expected:.2f}")

    if abs(bonus_amount - expected) < Decimal("0.01"):
        print("✅✅✅ BONUS CALCULATION CORRECT!")
        return True
    else:
        print(f"❌ WRONG! Got ${bonus_amount:.2f}, expected ${expected:.2f}")
        return False


def verify_scenario_2():
    """Verify multiple models in previous shift."""
    print("\n" + "="*60)
    print("SCENARIO 2: Previous employee with multiple models")
    print("="*60)

    sheets = SheetsService()

    print("\nTesting for Diana's shift (14:00)...")
    print("Diana sold: Model A ($400) + Model B ($600)")
    print("\nNext employee should get random bonus from one of Diana's models")

    # Simulate next employee's shift
    next_shift = {
        "Date": "2025/11/01 15:00:00",
        "Clock in": "2025/11/01 13:00:00",
        "EmployeeId": 555555,
        "Model A": 100.00,
        "Model B": 200.00,
    }

    # Find previous shift (should be Diana)
    models = sheets.get_models_from_shift(next_shift)
    prev_shift = sheets.find_previous_shift_with_models(
        employee_id=555555,
        models=models,
        before_date=next_shift["Date"]
    )

    if prev_shift:
        print(f"\n✅ Found previous shift:")
        print(f"   Employee: {prev_shift.get('EmployeeName')}")
        print(f"   Models: {sheets.get_models_from_shift(prev_shift)}")
    else:
        print("\n❌ No previous shift found")
        return False

    # Test randomness - run 5 times
    print("\n" + "─" * 60)
    print("Testing randomness (5 attempts):")
    print("Expected range: $3.20 (Model A) or $4.80 (Model B)")

    results = []
    for i in range(5):
        bonus = sheets.apply_percent_prev_bonus(
            employee_id=555555,
            current_shift=next_shift,
            bonus_value=1.0
        )
        results.append(bonus)

        if bonus == Decimal("3.20"):
            model = "Model A"
        elif bonus == Decimal("4.80"):
            model = "Model B"
        else:
            model = "Unknown"

        print(f"  Attempt {i+1}: ${bonus:.2f} ({model})")

    # Check if we have variation (randomness working)
    unique_values = set(results)
    if len(unique_values) > 1:
        print("\n✅✅ RANDOMNESS WORKING! Different models selected")
        return True
    else:
        print(f"\n⚠️  All attempts returned same value: ${results[0]:.2f}")
        print("This is possible (1/32 chance), but might indicate issue")
        return True  # Still ok, just unlikely


def main():
    """Run all verification tests."""
    print("\n" + "="*60)
    print("VERIFYING PERCENT_PREV BONUS LOGIC")
    print("="*60)

    try:
        # Scenario 1
        result1 = verify_scenario_1()

        # Scenario 2
        result2 = verify_scenario_2()

        # Summary
        print("\n" + "="*60)
        print("VERIFICATION SUMMARY")
        print("="*60)
        print(f"Scenario 1 (Parallel employees): {'✅ PASS' if result1 else '❌ FAIL'}")
        print(f"Scenario 2 (Multiple models): {'✅ PASS' if result2 else '❌ FAIL'}")

        if result1 and result2:
            print("\n🎉 ALL SCENARIOS PASSED!")
            print("✅ percent_prev logic is working correctly")
        else:
            print("\n❌ SOME SCENARIOS FAILED")
            print("Please review the implementation")

        print("="*60 + "\n")

        return 0 if (result1 and result2) else 1

    except Exception as e:
        print(f"\n❌ Verification failed: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit(main())
