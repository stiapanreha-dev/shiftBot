"""Test complex bonuses (percent_prev and percent_all)."""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))
import logging
from decimal import Decimal
from datetime import datetime

from sheets_service import SheetsService
from time_utils import format_dt, now_et

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def test_get_models_from_shift():
    """Test extracting models from shift."""
    print("\n" + "="*60)
    print("TEST 1: Get Models from Shift")
    print("="*60)

    sheets = SheetsService()

    # Mock shift with products
    shift = {
        "Model A": "100.00",
        "Model B": "200.00",
        "Model C": "",
        "Total sales": "300.00",
    }

    models = sheets.get_models_from_shift(shift)
    print(f"Models in shift: {models}")

    expected = ["Model A", "Model B"]
    if set(models) == set(expected):
        print("✅ Test passed")
    else:
        print(f"❌ Test failed: expected {expected}, got {models}")


def test_find_previous_shift():
    """Test finding previous shift with models."""
    print("\n" + "="*60)
    print("TEST 2: Find Previous Shift")
    print("="*60)

    sheets = SheetsService()
    employee_id = 120962578

    # Get a recent shift
    recent_shifts = sheets.get_last_shifts(employee_id, limit=1)
    if not recent_shifts:
        print("❌ No shifts found for employee")
        return

    shift = recent_shifts[0]
    models = sheets.get_models_from_shift(shift)

    print(f"Current shift ID: {shift.get('ID')}")
    print(f"Current shift models: {models}")
    print(f"Current shift date: {shift.get('Date')}")

    # Find previous shift
    prev_shift = sheets.find_previous_shift_with_models(
        employee_id=employee_id,
        models=models,
        before_date=shift.get("Date", "")
    )

    if prev_shift:
        print(f"✅ Found previous shift ID: {prev_shift.get('ID')}")
        print(f"   Employee: {prev_shift.get('EmployeeId')}")
        print(f"   Date: {prev_shift.get('Date')}")
        print(f"   Models: {sheets.get_models_from_shift(prev_shift)}")
    else:
        print("⚠️  No previous shift found (might be first shift with these models)")


def test_find_shifts_with_model():
    """Test finding all shifts with specific model."""
    print("\n" + "="*60)
    print("TEST 3: Find Shifts with Model")
    print("="*60)

    sheets = SheetsService()
    employee_id = 120962578

    # Get a recent shift
    recent_shifts = sheets.get_last_shifts(employee_id, limit=1)
    if not recent_shifts:
        print("❌ No shifts found for employee")
        return

    shift = recent_shifts[0]
    models = sheets.get_models_from_shift(shift)

    if not models:
        print("❌ No models in shift")
        return

    model = models[0]
    print(f"Current shift ID: {shift.get('ID')}")
    print(f"Searching for model: {model}")
    print(f"Date: {shift.get('Date')}")

    # Find shifts with this model
    matching_shifts = sheets.find_shifts_with_model(
        model=model,
        date=shift.get("Date", ""),
        exclude_employee=employee_id,
        before_time=shift.get("Clock in", "")
    )

    print(f"✅ Found {len(matching_shifts)} matching shifts")
    for s in matching_shifts:
        print(f"   Shift {s.get('ID')}: {s.get('EmployeeName')} - ${s.get(model)}")


def test_apply_percent_prev_bonus():
    """Test percent_prev bonus calculation."""
    print("\n" + "="*60)
    print("TEST 4: Apply percent_prev Bonus")
    print("="*60)

    sheets = SheetsService()
    employee_id = 120962578

    # Get a recent shift
    recent_shifts = sheets.get_last_shifts(employee_id, limit=1)
    if not recent_shifts:
        print("❌ No shifts found for employee")
        return

    shift = recent_shifts[0]

    # Calculate bonus
    bonus_amount = sheets.apply_percent_prev_bonus(
        employee_id=employee_id,
        current_shift=shift,
        bonus_value=1.0  # 1%
    )

    print(f"✅ Bonus amount: ${bonus_amount:.2f}")


def test_apply_percent_all_bonus():
    """Test percent_all bonus calculation."""
    print("\n" + "="*60)
    print("TEST 5: Apply percent_all Bonus")
    print("="*60)

    sheets = SheetsService()
    employee_id = 120962578

    # Get a recent shift
    recent_shifts = sheets.get_last_shifts(employee_id, limit=1)
    if not recent_shifts:
        print("❌ No shifts found for employee")
        return

    shift = recent_shifts[0]

    # Calculate bonus
    bonus_amount = sheets.apply_percent_all_bonus(
        employee_id=employee_id,
        current_shift=shift,
        bonus_value=2.0  # 2%
    )

    print(f"✅ Bonus amount: ${bonus_amount:.2f}")


def main():
    """Run all tests."""
    print("\n" + "="*60)
    print("TESTING COMPLEX BONUSES")
    print("="*60)

    try:
        test_get_models_from_shift()
        test_find_previous_shift()
        test_find_shifts_with_model()
        test_apply_percent_prev_bonus()
        test_apply_percent_all_bonus()

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
