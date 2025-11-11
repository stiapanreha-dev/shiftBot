"""Demo script to test rank bonus system."""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))
import logging
from decimal import Decimal

from sheets_service import SheetsService
from rank_service import RankService
from time_utils import format_dt, now_et

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def demo_rank_bonus():
    """Demonstrate rank bonus system with test data."""
    print("\n" + "="*60)
    print("DEMO: RANK BONUS SYSTEM")
    print("="*60)

    sheets = SheetsService()
    rank_service = RankService(sheets)

    # Test employee
    test_employee_id = 999999
    test_employee_name = "TestUser_RankDemo"

    now = now_et()
    year = now.year
    month = now.month
    base_date = now.strftime("%Y/%m/%d")

    print(f"\nTest Employee ID: {test_employee_id}")
    print(f"Month/Year: {month}/{year}")

    # Step 1: Create initial shift with low sales (Rookie)
    print("\n" + "="*60)
    print("STEP 1: Create shift with low sales ($500)")
    print("="*60)

    shift1_data = {
        "employee_id": test_employee_id,
        "employee_name": test_employee_name,
        "date": f"{base_date} 10:00:00",
        "clock_in": f"{base_date} 08:00:00",
        "clock_out": f"{base_date} 16:00:00",
        "products": {
            "Model A": 500.00,
        }
    }

    try:
        shift1_id = sheets.create_shift(shift1_data)
        print(f"✅ Shift {shift1_id} created")

        # Check rank
        rank_change = rank_service.check_and_update_rank(test_employee_id, year, month)
        if rank_change:
            print(f"   Rank: {rank_change.get('new_rank')}")
            print(f"   Bonus: {rank_change.get('bonus', 'None')}")
        else:
            # Get current rank
            rank = sheets.determine_rank(test_employee_id, year, month)
            print(f"   Rank: {rank}")
            print(f"   Bonus: None (initial Rookie rank)")

    except Exception as e:
        print(f"❌ Error: {e}")
        return

    # Step 2: Add more shifts to reach Hustler threshold ($2000+)
    print("\n" + "="*60)
    print("STEP 2: Create shift with $1800 sales (Total: $2300)")
    print("="*60)

    shift2_data = {
        "employee_id": test_employee_id,
        "employee_name": test_employee_name,
        "date": f"{base_date} 14:00:00",
        "clock_in": f"{base_date} 12:00:00",
        "clock_out": f"{base_date} 20:00:00",
        "products": {
            "Model B": 1800.00,
        }
    }

    try:
        shift2_id = sheets.create_shift(shift2_data)
        print(f"✅ Shift {shift2_id} created")

        # Check rank (should be Hustler now)
        rank_change = rank_service.check_and_update_rank(test_employee_id, year, month)
        if rank_change and rank_change.get("changed"):
            print(f"\n🎉 RANK UP!")
            print(f"   {rank_change.get('old_rank')} → {rank_change.get('new_rank')} {rank_change.get('emoji')}")

            bonus = rank_change.get('bonus')
            if bonus:
                print(f"   Bonus awarded: {bonus}")

                # Apply bonus
                rank_service.apply_rank_bonus(test_employee_id, bonus, shift2_id)
                print(f"   ✅ Bonus applied!")
            else:
                print(f"   No bonus (rank: {rank_change.get('new_rank')})")
        else:
            rank = sheets.determine_rank(test_employee_id, year, month)
            print(f"   Rank unchanged: {rank}")

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return

    # Step 3: Show ActiveBonuses table
    print("\n" + "="*60)
    print("ACTIVE BONUSES TABLE")
    print("="*60)

    import gspread
    from config import Config

    client = gspread.service_account(filename=Config.GOOGLE_SA_JSON)
    spreadsheet = client.open_by_key(Config.SPREADSHEET_ID)
    ws = spreadsheet.worksheet("ActiveBonuses")

    data = ws.get_all_values()

    for i, row in enumerate(data):
        if i == 0:
            print("\nHeaders:")
            print(" | ".join(row))
            print("-" * 80)
        else:
            if row[0]:  # If ID exists
                print(" | ".join(row))

    # Step 4: Show EmployeeRanks for test user
    print("\n" + "="*60)
    print("EMPLOYEE RANKS (Test User)")
    print("="*60)

    ws = spreadsheet.worksheet("EmployeeRanks")
    all_records = ws.get_all_records()

    for record in all_records:
        if str(record.get("EmployeeId")) == str(test_employee_id):
            print(f"\nEmployee: {test_employee_id}")
            print(f"Current Rank: {record.get('Current Rank')}")
            print(f"Previous Rank: {record.get('Previous Rank')}")
            print(f"Month/Year: {record.get('Month')}/{record.get('Year')}")
            print(f"Notified: {record.get('Notified')}")
            print(f"Last Updated: {record.get('Last Updated')}")

    print("\n" + "="*60)
    print("✅ DEMO COMPLETED")
    print("="*60)
    print("\nSummary:")
    print(f"- Created 2 shifts for test employee {test_employee_id}")
    print(f"- Total sales: $2300")
    print(f"- Rank: Rookie → Hustler")
    print(f"- Bonus created in ActiveBonuses table")
    print()
    print("⚠️  Note: Test data added. Clean up if needed:")
    print(f"   - Delete shifts for employee {test_employee_id}")
    print(f"   - Delete EmployeeRanks record for {test_employee_id}")
    print(f"   - Delete ActiveBonuses record if needed")
    print()


def main():
    """Main entry point."""
    try:
        demo_rank_bonus()
        return 0
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit(main())
