"""Check shifts created today for user."""

import sys
import os
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from sheets_service import SheetsService
from time_utils import now_et

sheets = SheetsService()
today = now_et().strftime('%Y/%m/%d')
all_shifts = sheets.get_all_shifts()

user_id = 120962578
user_shifts_today = [s for s in all_shifts if s.get('EmployeeId') == user_id and s.get('Date', '').startswith(today)]

print(f'📊 Смен пользователя {user_id} сегодня ({today}): {len(user_shifts_today)}')
print(f'Total sales за день: ${sum(s.get("Total sales", 0) for s in user_shifts_today):.2f}')
print()

for s in user_shifts_today:
    shift_id = s.get("ID")
    total_sales = s.get("Total sales", 0)
    commission_pct = s.get("%", 0)
    print(f'  Shift {shift_id}: ${total_sales:.2f} (Commission %: {commission_pct:.2f}%)')
