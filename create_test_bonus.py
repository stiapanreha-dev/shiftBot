#!/usr/bin/env python3
"""Create a test bonus for testing."""

from sheets_service import SheetsService
from time_utils import format_dt, now_et

def main():
    sheets = SheetsService()

    employee_id = 120962578
    bonus_type = "percent_next"
    bonus_value = 3.0  # +3% commission

    print(f"Creating test bonus for employee {employee_id}...")
    print(f"  Type: {bonus_type}")
    print(f"  Value: {bonus_value}%")
    print()

    created_at = format_dt(now_et())

    bonus_id = sheets.create_bonus(
        employee_id=employee_id,
        bonus_type=bonus_type,
        value=bonus_value,
        created_at=created_at
    )

    if bonus_id:
        print(f"✅ Bonus created successfully!")
        print(f"   Bonus ID: {bonus_id}")
        print()
        print("Now create a new shift in the bot to see the bonus applied!")
    else:
        print("❌ Failed to create bonus")

if __name__ == "__main__":
    main()
