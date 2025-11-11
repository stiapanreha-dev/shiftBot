"""Test percent_prev bonus with complex scenario: 2 parallel employees."""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))
import logging
from decimal import Decimal
from datetime import datetime, timedelta

from sheets_service import SheetsService
from time_utils import format_dt, now_et, parse_dt

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def create_test_data():
    """Create test data for percent_prev scenario."""
    print("\n" + "="*60)
    print("CREATING TEST DATA")
    print("="*60)

    sheets = SheetsService()

    # Current time
    now = now_et()

    # Create test scenario:
    # Employee 1 (111): sold Model A at 10:00
    # Employee 2 (222): sold Model B at 11:00
    # Employee 3 (333): will get bonus at 12:00, selling Model A and Model B

    base_date = now.strftime("%Y/%m/%d")

    # Shift 1: Employee 111, 10:00, Model A only
    shift1_data = {
        "employee_id": 111,
        "employee_name": "TestUser1",
        "date": f"{base_date} 10:00:00",
        "clock_in": f"{base_date} 08:00:00",
        "clock_out": f"{base_date} 16:00:00",
        "products": {
            "Model A": 500.00,
        }
    }

    # Shift 2: Employee 222, 11:00, Model B only
    shift2_data = {
        "employee_id": 222,
        "employee_name": "TestUser2",
        "date": f"{base_date} 11:00:00",
        "clock_in": f"{base_date} 09:00:00",
        "clock_out": f"{base_date} 17:00:00",
        "products": {
            "Model B": 800.00,
        }
    }

    try:
        print("\nCreating shift 1 (Employee 111, Model A, 10:00)...")
        shift1_id = sheets.create_shift(shift1_data)
        print(f"✅ Shift {shift1_id} created")

        print("\nCreating shift 2 (Employee 222, Model B, 11:00)...")
        shift2_id = sheets.create_shift(shift2_data)
        print(f"✅ Shift {shift2_id} created")

        print("\n" + "="*60)
        print("TEST DATA CREATED SUCCESSFULLY")
        print("="*60)
        print(f"\nShift {shift1_id}: Employee 111, Model A=$500, Date={base_date} 10:00")
        print(f"Shift {shift2_id}: Employee 222, Model B=$800, Date={base_date} 11:00")

        return shift1_id, shift2_id, base_date

    except Exception as e:
        print(f"\n❌ Error creating test data: {e}")
        import traceback
        traceback.print_exc()
        return None, None, None


def test_percent_prev_with_parallel_employees():
    """Test percent_prev bonus selection logic."""
    print("\n" + "="*60)
    print("TEST: Percent_prev with 2 parallel employees")
    print("="*60)

    sheets = SheetsService()

    # Create test data
    shift1_id, shift2_id, base_date = create_test_data()

    if not shift1_id or not shift2_id:
        print("❌ Failed to create test data")
        return

    print("\n" + "="*60)
    print("SCENARIO:")
    print("="*60)
    print("Current employee (333) will sell Model A + Model B at 12:00")
    print("Previous employees:")
    print("  - Employee 111: Model A only at 10:00")
    print("  - Employee 222: Model B only at 11:00")
    print("\nExpected: Should select Employee 222 (11:00 is closer to 12:00)")
    print("="*60)

    # Simulate current shift for employee 333
    current_shift = {
        "Date": f"{base_date} 12:00:00",
        "Clock in": f"{base_date} 10:00:00",
        "EmployeeId": 333,
        "Model A": 300.00,
        "Model B": 200.00,
    }

    # Test find_previous_shift_with_models
    print("\nFinding previous shift...")
    models = sheets.get_models_from_shift(current_shift)
    print(f"Current shift models: {models}")

    prev_shift = sheets.find_previous_shift_with_models(
        employee_id=333,
        models=models,
        before_date=current_shift["Date"]
    )

    if prev_shift:
        print(f"\n✅ Found previous shift:")
        print(f"   ID: {prev_shift.get('ID')}")
        print(f"   Employee: {prev_shift.get('EmployeeId')} ({prev_shift.get('EmployeeName')})")
        print(f"   Date: {prev_shift.get('Date')}")
        print(f"   Models: {sheets.get_models_from_shift(prev_shift)}")

        # Check if it's the correct one (Employee 222, 11:00)
        if str(prev_shift.get('EmployeeId')) == '222':
            print("\n✅✅ CORRECT! Selected Employee 222 (closest date)")
        else:
            print(f"\n❌ WRONG! Selected Employee {prev_shift.get('EmployeeId')} instead of 222")
    else:
        print("\n❌ No previous shift found")
        return

    # Test apply_percent_prev_bonus
    print("\n" + "="*60)
    print("Applying percent_prev bonus (1%)...")
    print("="*60)

    bonus_amount = sheets.apply_percent_prev_bonus(
        employee_id=333,
        current_shift=current_shift,
        bonus_value=1.0  # 1%
    )

    print(f"\n💰 Bonus amount: ${bonus_amount:.2f}")

    # Calculate expected bonus
    # Employee 222 sold Model B = $800
    # Net sales = $800 × 0.8 = $640
    # Bonus 1% = $640 × 0.01 = $6.40
    expected_bonus = Decimal("6.40")

    print(f"Expected bonus: ${expected_bonus:.2f}")

    if abs(bonus_amount - expected_bonus) < Decimal("0.01"):
        print("\n✅✅✅ BONUS CALCULATION CORRECT!")
    else:
        print(f"\n❌ BONUS CALCULATION WRONG! Got ${bonus_amount:.2f}, expected ${expected_bonus:.2f}")


def test_percent_prev_with_multiple_models():
    """Test percent_prev when previous employee sold multiple models."""
    print("\n" + "="*60)
    print("TEST: Percent_prev with previous employee having multiple models")
    print("="*60)

    sheets = SheetsService()
    now = now_et()
    base_date = now.strftime("%Y/%m/%d")

    # Create shift with multiple models for Employee 444
    shift_data = {
        "employee_id": 444,
        "employee_name": "TestUser4",
        "date": f"{base_date} 14:00:00",
        "clock_in": f"{base_date} 12:00:00",
        "clock_out": f"{base_date} 20:00:00",
        "products": {
            "Model A": 400.00,
            "Model B": 600.00,
        }
    }

    try:
        print("\nCreating shift (Employee 444, Model A + Model B, 14:00)...")
        shift_id = sheets.create_shift(shift_data)
        print(f"✅ Shift {shift_id} created")

        # Simulate current shift for employee 555
        current_shift = {
            "Date": f"{base_date} 15:00:00",
            "Clock in": f"{base_date} 13:00:00",
            "EmployeeId": 555,
            "Model A": 100.00,
            "Model B": 200.00,
        }

        print("\n" + "="*60)
        print("SCENARIO:")
        print("="*60)
        print("Previous employee (444) sold Model A ($400) + Model B ($600)")
        print("Current employee (555) sold Model A ($100) + Model B ($200)")
        print("\nExpected: Random selection of Model A or Model B from previous shift")
        print("="*60)

        # Apply bonus multiple times to see randomness
        print("\nApplying bonus 5 times to test randomness:")
        for i in range(5):
            bonus = sheets.apply_percent_prev_bonus(
                employee_id=555,
                current_shift=current_shift,
                bonus_value=1.0
            )
            print(f"  Attempt {i+1}: ${bonus:.2f}")

        print("\n✅ Test completed - check logs for selected models")

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()


def cleanup_test_data():
    """Clean up test data."""
    print("\n" + "="*60)
    print("CLEANUP")
    print("="*60)
    print("⚠️  Manual cleanup required:")
    print("   Please delete test shifts for employees 111, 222, 444, 555")
    print("   from Google Sheets if needed")


def main():
    """Run all tests."""
    print("\n" + "="*60)
    print("PERCENT_PREV BONUS - DETAILED TESTING")
    print("="*60)

    try:
        # Test 1: Two parallel employees
        test_percent_prev_with_parallel_employees()

        # Test 2: Multiple models in previous shift
        test_percent_prev_with_multiple_models()

        # Cleanup
        cleanup_test_data()

        print("\n" + "="*60)
        print("✅ ALL TESTS COMPLETED")
        print("="*60 + "\n")

    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return 1

    return 0


if __name__ == "__main__":
    exit(main())
