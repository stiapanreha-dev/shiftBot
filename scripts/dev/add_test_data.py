"""Add test data to Google Sheets for percent_prev testing."""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))
import gspread
from config import Config
from datetime import datetime

def add_test_data():
    """Add test shifts to demonstrate percent_prev logic."""
    print("\n" + "="*60)
    print("ADDING TEST DATA FOR PERCENT_PREV TESTING")
    print("="*60)

    client = gspread.service_account(filename=Config.GOOGLE_SA_JSON)
    spreadsheet = client.open_by_key(Config.SPREADSHEET_ID)
    ws = spreadsheet.worksheet("Shifts")

    # Get next ID
    all_values = ws.get_all_values()
    last_id = 0
    for row in all_values[1:]:
        if row[0]:  # If ID exists
            try:
                last_id = max(last_id, int(row[0]))
            except:
                pass

    next_id = last_id + 1
    print(f"\nNext shift ID: {next_id}")

    # Test scenario date: Today
    base_date = "2025/11/01"

    # Create test data
    test_shifts = [
        {
            "ID": next_id,
            "Date": f"{base_date} 10:00:00",
            "EmployeeId": "111111",
            "EmployeeName": "TestUser_Alice",
            "Clock in": f"{base_date} 08:00:00",
            "Clock out": f"{base_date} 16:00:00",
            "Worked hours/shift": "8.00",
            "Model A": "500.00",
            "Model B": "",
            "Model C": "",
            "Total sales": "500.00",
            "Net sales": "400.00",
            "%": "10.00",
            "Total per hour": "120.00",
            "Commissions": "40.00",
            "Total made": "160.00"
        },
        {
            "ID": next_id + 1,
            "Date": f"{base_date} 11:00:00",
            "EmployeeId": "222222",
            "EmployeeName": "TestUser_Bob",
            "Clock in": f"{base_date} 09:00:00",
            "Clock out": f"{base_date} 17:00:00",
            "Worked hours/shift": "8.00",
            "Model A": "",
            "Model B": "800.00",
            "Model C": "",
            "Total sales": "800.00",
            "Net sales": "640.00",
            "%": "10.00",
            "Total per hour": "120.00",
            "Commissions": "64.00",
            "Total made": "184.00"
        },
        {
            "ID": next_id + 2,
            "Date": f"{base_date} 12:30:00",
            "EmployeeId": "333333",
            "EmployeeName": "TestUser_Charlie",
            "Clock in": f"{base_date} 10:00:00",
            "Clock out": f"{base_date} 18:00:00",
            "Worked hours/shift": "8.00",
            "Model A": "300.00",
            "Model B": "200.00",
            "Model C": "",
            "Total sales": "500.00",
            "Net sales": "400.00",
            "%": "10.00",
            "Total per hour": "120.00",
            "Commissions": "40.00",
            "Total made": "160.00"
        },
        {
            "ID": next_id + 3,
            "Date": f"{base_date} 14:00:00",
            "EmployeeId": "444444",
            "EmployeeName": "TestUser_Diana",
            "Clock in": f"{base_date} 12:00:00",
            "Clock out": f"{base_date} 20:00:00",
            "Worked hours/shift": "8.00",
            "Model A": "400.00",
            "Model B": "600.00",
            "Model C": "",
            "Total sales": "1000.00",
            "Net sales": "800.00",
            "%": "12.00",
            "Total per hour": "120.00",
            "Commissions": "96.00",
            "Total made": "216.00"
        }
    ]

    # Get headers
    headers = ws.row_values(1)

    print("\nAdding test shifts:")
    print("="*60)

    for shift in test_shifts:
        # Build row according to headers
        row = []
        for header in headers:
            row.append(shift.get(header, ""))

        # Append row
        ws.append_row(row, value_input_option="RAW")

        print(f"✅ Shift {shift['ID']}: {shift['EmployeeName']}")
        print(f"   Date: {shift['Date']}")
        print(f"   Models: A=${shift['Model A']}, B=${shift['Model B']}, C=${shift['Model C']}")
        print()

    print("="*60)
    print("✅ TEST DATA ADDED SUCCESSFULLY")
    print("="*60)

    # Print scenario explanation
    print("\n" + "="*60)
    print("TEST SCENARIOS CREATED")
    print("="*60)

    print("\n📋 SCENARIO 1: Two parallel employees")
    print("─" * 60)
    print(f"Shift {next_id}: Alice (10:00) sold Model A = $500")
    print(f"Shift {next_id + 1}: Bob (11:00) sold Model B = $800")
    print(f"Shift {next_id + 2}: Charlie (12:30) sold Model A + Model B")
    print("\n🧪 Test percent_prev for Charlie:")
    print("   Expected: Select Bob's shift (11:00 is closer to 12:30)")
    print("   Bob sold Model B = $800")
    print("   Net sales = $800 × 0.8 = $640")
    print("   Bonus 1% = $640 × 0.01 = $6.40")

    print("\n📋 SCENARIO 2: Previous employee with multiple models")
    print("─" * 60)
    print(f"Shift {next_id + 3}: Diana (14:00) sold Model A ($400) + Model B ($600)")
    print("\n🧪 Test percent_prev for next employee:")
    print("   Expected: Random selection of Model A or Model B")
    print("   If Model A selected: $400 × 0.8 × 0.01 = $3.20")
    print("   If Model B selected: $600 × 0.8 × 0.01 = $4.80")

    print("\n" + "="*60)
    print("VIEW DATA IN GOOGLE SHEETS")
    print("="*60)
    print(f"Spreadsheet ID: {Config.SPREADSHEET_ID}")
    print(f"Sheet: Shifts")
    print(f"Test shifts IDs: {next_id} - {next_id + 3}")
    print()


def main():
    """Main entry point."""
    try:
        Config.validate()
        add_test_data()

        print("\n💡 NEXT STEPS:")
        print("1. Open Google Sheets and verify test data")
        print("2. Run: python3 verify_percent_prev.py")
        print("3. Check the logic works correctly")
        print()

        return 0

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit(main())
