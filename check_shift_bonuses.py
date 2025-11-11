#!/usr/bin/env python3
"""Check bonuses applied to shift 26."""

from sheets_service import SheetsService

def main():
    sheets = SheetsService()

    shift_id = 26
    employee_id = 120962578

    print(f"Checking bonuses for shift {shift_id}...")
    print()

    # Get shift data
    shift = sheets.get_shift_by_id(shift_id)
    if shift:
        print(f"Shift {shift_id} found:")
        print(f"  Employee: {shift.get('EmployeeName')} (ID: {shift.get('EmployeeId')})")
        print(f"  Date: {shift.get('Date')}")
        print(f"  Total sales: ${shift.get('Total sales', 0)}")
        print(f"  Commission %: {shift.get('%', 0)}")
        print()

    # Get applied bonuses for this shift
    applied_bonuses = sheets.get_shift_applied_bonuses(shift_id)

    if applied_bonuses:
        print(f"Found {len(applied_bonuses)} applied bonus(es) for shift {shift_id}:")
        for bonus in applied_bonuses:
            print(f"  - ID: {bonus.get('ID')}")
            print(f"    Type: {bonus.get('Bonus Type')}")
            print(f"    Value: {bonus.get('Value')}")
            print(f"    Applied: {bonus.get('Applied')}")
            print(f"    Shift ID: {bonus.get('Shift ID')}")
            print()
    else:
        print(f"No bonuses applied to shift {shift_id}")

    # Check active bonuses for this employee
    print(f"\nChecking active bonuses for employee {employee_id}...")
    active_bonuses = sheets.get_active_bonuses(employee_id)

    if active_bonuses:
        print(f"Found {len(active_bonuses)} active bonus(es):")
        for bonus in active_bonuses:
            print(f"  - ID: {bonus.get('ID')}")
            print(f"    Type: {bonus.get('Bonus Type')}")
            print(f"    Value: {bonus.get('Value')}")
            print(f"    Applied: {bonus.get('Applied')}")
            print()
    else:
        print("No active bonuses found")

if __name__ == "__main__":
    main()
