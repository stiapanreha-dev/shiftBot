"""Delete specific shifts from Google Sheets."""

import sys
import os
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from sheets_service import SheetsService

def delete_shifts(shift_ids: list):
    """Delete shifts by ID.

    Args:
        shift_ids: List of shift IDs to delete
    """
    sheets = SheetsService()

    print(f"🗑️  Deleting shifts: {shift_ids}")
    print()

    # Get all shifts
    all_shifts = sheets.get_all_shifts()

    # Find row numbers for these shifts (ID is in column A, row 2 is first data row)
    rows_to_delete = []

    for shift in all_shifts:
        if shift.get('ID') in shift_ids:
            # Find the row index (1-based, +2 because header is row 1, data starts at row 2)
            row_index = all_shifts.index(shift) + 2
            rows_to_delete.append(row_index)
            print(f"  Shift {shift.get('ID')} found at row {row_index}")

    if not rows_to_delete:
        print("❌ No shifts found to delete")
        return

    # Delete rows in reverse order to maintain row indices
    rows_to_delete.sort(reverse=True)

    worksheet = sheets.get_worksheet()

    for row_index in rows_to_delete:
        print(f"  Deleting row {row_index} (Shift ID: {all_shifts[row_index-2].get('ID')})")
        worksheet.delete_rows(row_index)

    print()
    print(f"✅ Successfully deleted {len(rows_to_delete)} shift(s)")

    # Show remaining shifts count
    remaining_shifts = sheets.get_all_shifts()
    print(f"📊 Remaining shifts in database: {len(remaining_shifts)}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 delete_shifts.py <shift_id1> <shift_id2> ...")
        sys.exit(1)

    shift_ids = [int(sid) for sid in sys.argv[1:]]
    delete_shifts(shift_ids)
