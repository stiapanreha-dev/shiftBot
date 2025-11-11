#!/usr/bin/env python3
"""Simple import: Shifts from Google Sheets to PostgreSQL."""

import os
import sys
sys.path.insert(0, '/home/lexun/Alex12060')
os.chdir('/home/lexun/Alex12060')

from dotenv import load_dotenv
load_dotenv()

import gspread
import psycopg2
from decimal import Decimal

# Connect
print("Connecting to Google Sheets...")
sheets_client = gspread.service_account(filename='google_sheets_credentials.json')
spreadsheet = sheets_client.open_by_key(os.getenv('SPREADSHEET_ID'))
print(f"✓ Connected: {spreadsheet.title}")

print("Connecting to PostgreSQL...")
db_conn = psycopg2.connect(
    host=os.getenv('DB_HOST'),
    database=os.getenv('DB_NAME'),
    user=os.getenv('DB_USER'),
    password=os.getenv('DB_PASSWORD')
)
cursor = db_conn.cursor()
print("✓ Connected to PostgreSQL")

# Get product mapping
cursor.execute("SELECT id, name FROM products")
product_map = {row[1]: row[0] for row in cursor.fetchall()}
print(f"✓ Found {len(product_map)} products")

# Import shifts
ws = spreadsheet.worksheet('Shifts')
records = ws.get_all_records()
print(f"\nImporting {len(records)} shifts...")

from config import Config

imported = 0
skipped = 0

for i, record in enumerate(records, 1):
    try:
        shift_id = int(record.get('ID', 0))
        if shift_id == 0 or not record.get('Date'):
            continue

        employee_id = int(record.get('EmployeeId', 0))
        employee_name = record.get('EmployeeName', f'Employee {employee_id}')

        # Ensure employee exists
        cursor.execute("""
            INSERT INTO employees (id, name, telegram_id, is_active)
            VALUES (%s, %s, %s, true)
            ON CONFLICT (id) DO NOTHING
        """, (employee_id, employee_name, employee_id))

        # Parse data safely
        def safe_decimal(val):
            try:
                return Decimal(str(val)) if val else Decimal('0')
            except:
                return Decimal('0')

        # Insert shift
        cursor.execute("""
            INSERT INTO shifts (
                id, date, employee_id, employee_name,
                clock_in, clock_out, worked_hours,
                total_sales, net_sales, commission_pct,
                total_per_hour, commissions, total_made
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (id) DO NOTHING
            RETURNING id
        """, (
            shift_id,
            record.get('Date'),
            employee_id,
            employee_name,
            record.get('Clock in'),
            record.get('Clock out'),
            safe_decimal(record.get('Worked hours/shift')),
            safe_decimal(record.get('Total sales')),
            safe_decimal(record.get('Net sales')),
            safe_decimal(record.get('%')),
            safe_decimal(record.get('Total per hour')),
            safe_decimal(record.get('Commissions')),
            safe_decimal(record.get('Total made'))
        ))

        if cursor.fetchone():
            # Import products
            for product_name in Config.PRODUCTS:
                amount = safe_decimal(record.get(product_name))
                if amount > 0 and product_name in product_map:
                    cursor.execute("""
                        INSERT INTO shift_products (shift_id, product_id, amount)
                        VALUES (%s, %s, %s)
                        ON CONFLICT DO NOTHING
                    """, (shift_id, product_map[product_name], amount))

            imported += 1
            db_conn.commit()  # Commit after each successful import

            if i % 50 == 0:
                print(f"  Progress: {i}/{len(records)}...")
        else:
            skipped += 1

    except Exception as e:
        print(f"  Error shift {shift_id}: {e}")
        db_conn.rollback()  # Rollback this shift only

# Final commit
db_conn.commit()
db_conn.close()

print(f"\n✓ Imported: {imported} shifts")
print(f"✓ Skipped: {skipped} (already exist)")
print("\n✅ Import completed!")
