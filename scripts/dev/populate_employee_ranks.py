"""Populate EmployeeRanks table for existing shifts."""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))
import logging
from datetime import datetime

from sheets_service import SheetsService
from rank_service import RankService
from time_utils import parse_dt

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def populate_employee_ranks():
    """Populate EmployeeRanks for all existing shifts."""
    print("\n" + "="*60)
    print("POPULATING EMPLOYEE RANKS")
    print("="*60)

    sheets = SheetsService()
    rank_service = RankService(sheets)

    # Get all shifts
    all_shifts = sheets.get_all_shifts()

    if not all_shifts:
        print("❌ No shifts found")
        return

    print(f"\nFound {len(all_shifts)} total shifts")

    # Filter out test users
    test_employee_ids = ["111111", "222222", "333333", "444444", "555555"]
    real_shifts = [s for s in all_shifts
                   if str(s.get("EmployeeId")) not in test_employee_ids]

    print(f"Real user shifts: {len(real_shifts)}")

    # Group shifts by employee and month
    employee_months = {}

    for shift in real_shifts:
        employee_id = str(shift.get("EmployeeId"))
        date_str = shift.get("Date", "")

        if not employee_id or not date_str:
            continue

        try:
            date = parse_dt(date_str)
            year = date.year
            month = date.month

            key = (employee_id, year, month)

            if key not in employee_months:
                employee_months[key] = []

            employee_months[key].append(shift)
        except Exception as e:
            logger.warning(f"Failed to parse date for shift {shift.get('ID')}: {e}")
            continue

    print(f"\nUnique employee-months: {len(employee_months)}")
    print("\n" + "="*60)
    print("Processing...")
    print("="*60)

    # Process each employee-month
    processed = 0
    for (employee_id, year, month), shifts in employee_months.items():
        try:
            print(f"\nEmployee {employee_id} - {year}/{month:02d}")
            print(f"  Shifts in this month: {len(shifts)}")

            # Check and update rank
            rank_change = rank_service.check_and_update_rank(
                int(employee_id),
                year,
                month
            )

            if rank_change:
                if rank_change.get("changed"):
                    print(f"  ✅ Rank set: {rank_change.get('new_rank')}")
                else:
                    print(f"  ℹ️  Rank already set")
            else:
                print(f"  ✅ Initial rank created")

            processed += 1

        except Exception as e:
            print(f"  ❌ Error: {e}")
            logger.error(f"Failed to process {employee_id} {year}/{month}: {e}")

    print("\n" + "="*60)
    print(f"✅ COMPLETED: Processed {processed}/{len(employee_months)} employee-months")
    print("="*60)

    # Show EmployeeRanks table
    print("\n" + "="*60)
    print("EMPLOYEE RANKS TABLE")
    print("="*60)

    import gspread
    from config import Config

    client = gspread.service_account(filename=Config.GOOGLE_SA_JSON)
    spreadsheet = client.open_by_key(Config.SPREADSHEET_ID)
    ws = spreadsheet.worksheet("EmployeeRanks")

    data = ws.get_all_values()

    for i, row in enumerate(data):
        if i == 0:
            print("\nHeaders:")
            print(" | ".join(row))
            print("-" * 60)
        else:
            # EmployeeId, Current Rank, Month, Year
            print(f"Employee {row[0]} | {row[1]} | {row[3]}/{row[4]} | Updated: {row[6][:10]}")

    print()


def main():
    """Main entry point."""
    try:
        populate_employee_ranks()
        return 0
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit(main())
