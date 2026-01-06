#!/usr/bin/env python3
"""
Fix Google Sheets headers and resync all shifts.

This script:
1. Updates headers in Shifts worksheet (moves Models to end)
2. Clears all data rows (keeps headers)
3. Adds ALL shifts to sync_queue for re-synchronization

Usage:
    python fix_sheets_headers.py
"""

import os
import sys
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

import gspread
from google.oauth2.service_account import Credentials
import psycopg2


# Google Sheets setup
SCOPES = ['https://www.googleapis.com/auth/spreadsheets']
CREDENTIALS_FILE = 'google_sheets_credentials.json'
SPREADSHEET_ID = os.getenv('SPREADSHEET_ID', '1cAdHtGBaPH9EvisR0OwxKTd5PtpGlb5WF9wSq_X8x8E')

# Database setup
DB_CONFIG = {
    'host': os.getenv('DB_HOST', 'localhost'),
    'port': int(os.getenv('DB_PORT', 5432)),
    'dbname': os.getenv('DB_NAME', 'alex12060'),
    'user': os.getenv('DB_USER', 'alex12060_user'),
    'password': os.getenv('DB_PASSWORD', 'alex12060_pass'),
}

# New headers (Models at the end) - 19 columns
HEADERS = [
    'ID', 'Date', 'EmployeeID', 'EmployeeName', 'ClockIn', 'ClockOut', 'WorkedHours',
    'TotalSales', 'NetSales', 'CommissionPct', 'TotalHourly', 'Commissions', 'TotalMade',
    'RollingAverage', 'BonusCounter', 'ModelA', 'ModelB', 'ModelC', 'ModelD'
]


def main():
    print("=" * 60)
    print("Fix Google Sheets Headers and Resync All Shifts")
    print("=" * 60)

    # 1. Connect to Google Sheets
    print("\n[1/4] Connecting to Google Sheets...")
    try:
        creds = Credentials.from_service_account_file(CREDENTIALS_FILE, scopes=SCOPES)
        gc = gspread.authorize(creds)
        spreadsheet = gc.open_by_key(SPREADSHEET_ID)
        worksheet = spreadsheet.worksheet('Shifts')
        print(f"  Connected to spreadsheet: {spreadsheet.title}")
        print(f"  Worksheet: {worksheet.title}")
    except Exception as e:
        print(f"  ERROR: Failed to connect to Google Sheets: {e}")
        sys.exit(1)

    # 2. Update headers (row 1)
    print("\n[2/4] Updating headers...")
    try:
        worksheet.update('A1:S1', [HEADERS])
        print(f"  Headers updated: {', '.join(HEADERS)}")
    except Exception as e:
        print(f"  ERROR: Failed to update headers: {e}")
        sys.exit(1)

    # 3. Clear all data except headers
    print("\n[3/4] Clearing all data rows...")
    try:
        # Get row count
        all_values = worksheet.get_all_values()
        row_count = len(all_values)
        if row_count > 1:
            worksheet.batch_clear([f'A2:S{row_count + 1}'])
            print(f"  Cleared {row_count - 1} data rows (kept headers)")
        else:
            print("  No data rows to clear")
    except Exception as e:
        print(f"  ERROR: Failed to clear data: {e}")
        sys.exit(1)

    # 4. Add all shifts to sync_queue
    print("\n[4/4] Adding all shifts to sync_queue...")
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        with conn.cursor() as cur:
            # First, get count of shifts
            cur.execute("SELECT COUNT(*) FROM shifts")
            total_shifts = cur.fetchone()[0]
            print(f"  Total shifts in database: {total_shifts}")

            if total_shifts == 0:
                print("  No shifts to sync")
            else:
                # Add all shifts to sync_queue with high priority
                cur.execute("""
                    INSERT INTO sync_queue (table_name, record_id, operation, data, priority, status)
                    SELECT 'shifts', id, 'UPDATE', row_to_json(s)::jsonb, 1, 'pending'
                    FROM shifts s
                    ORDER BY id
                """)
                inserted = cur.rowcount
                conn.commit()
                print(f"  Added {inserted} shifts to sync_queue")

        conn.close()
    except Exception as e:
        print(f"  ERROR: Failed to add shifts to sync_queue: {e}")
        sys.exit(1)

    print("\n" + "=" * 60)
    print("DONE!")
    print("=" * 60)
    print("\nNext steps:")
    print("1. Restart sync worker: systemctl restart alex12060-sync-worker")
    print("2. Monitor logs: tail -f /opt/alex12060-bot/logs/sync_worker.log")
    print(f"3. Check Google Sheets: {spreadsheet.url}")


if __name__ == '__main__':
    main()
