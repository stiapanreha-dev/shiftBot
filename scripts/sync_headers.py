#!/usr/bin/env python3
"""Sync column headers in Google Sheets to match expected format."""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

import gspread
from google.oauth2.service_account import Credentials

# Expected headers for each sheet
SHEET_HEADERS = {
    'Shifts': [
        'ID', 'Date', 'EmployeeID', 'EmployeeName', 'ClockIn', 'ClockOut', 'WorkedHours',
        'ModelA', 'ModelB', 'ModelC', 'ModelD', 'TotalSales', 'NetSales', 'CommissionPct',
        'TotalHourly', 'Commissions', 'TotalMade', 'RollingAverage', 'BonusCounter'
    ],
    'ActiveBonuses': [
        'ID', 'EmployeeID', 'BonusType', 'Value', 'Applied', 'ShiftID', 'CreatedAt'
    ],
    'EmployeeRanks': [
        'EmployeeID', 'Year', 'Month', 'CurrentRank', 'PreviousRank', 'UpdatedAt', 'Notified'
    ],
    'EmployeeSettings': [
        'ID', 'Name', 'HourlyWage', 'SalesCommission', 'Active'
    ]
}

def main():
    spreadsheet_id = os.getenv('SPREADSHEET_ID')
    if not spreadsheet_id:
        print("ERROR: SPREADSHEET_ID not set in .env")
        return

    print(f"Connecting to spreadsheet: {spreadsheet_id}")

    # Connect to Google Sheets
    scopes = [
        'https://www.googleapis.com/auth/spreadsheets',
        'https://www.googleapis.com/auth/drive'
    ]
    creds = Credentials.from_service_account_file(
        'google_sheets_credentials.json', scopes=scopes
    )
    client = gspread.authorize(creds)
    spreadsheet = client.open_by_key(spreadsheet_id)

    print(f"Connected to: {spreadsheet.title}\n")

    for sheet_name, expected_headers in SHEET_HEADERS.items():
        try:
            worksheet = spreadsheet.worksheet(sheet_name)
            current_headers = worksheet.row_values(1)

            print(f"=== {sheet_name} ===")
            print(f"  Current:  {current_headers}")
            print(f"  Expected: {expected_headers}")

            if current_headers == expected_headers:
                print(f"  Status: OK\n")
            else:
                # Update headers
                last_col = chr(ord('A') + len(expected_headers) - 1)
                worksheet.update(f'A1:{last_col}1', [expected_headers])
                print(f"  Status: UPDATED\n")

        except gspread.WorksheetNotFound:
            print(f"=== {sheet_name} ===")
            print(f"  Status: SHEET NOT FOUND - creating...")
            worksheet = spreadsheet.add_worksheet(title=sheet_name, rows=1000, cols=len(expected_headers))
            last_col = chr(ord('A') + len(expected_headers) - 1)
            worksheet.update(f'A1:{last_col}1', [expected_headers])
            print(f"  Status: CREATED\n")

    print("Done!")

if __name__ == '__main__':
    main()
