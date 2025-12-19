#!/usr/bin/env python3
"""Sync pending records from PostgreSQL to Google Sheets."""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import psycopg2
from psycopg2.extras import RealDictCursor
import gspread
from google.oauth2.service_account import Credentials
from dotenv import load_dotenv

# Load environment
load_dotenv()

from services.sync import (
    ShiftSyncProcessor,
    BonusSyncProcessor,
    RankSyncProcessor,
    EmployeeSyncProcessor,
    FortnightSyncProcessor,
)

def main():
    print("=" * 60)
    print("Syncing PostgreSQL -> Google Sheets")
    print("=" * 60)

    # Connect to PostgreSQL
    db_conn = psycopg2.connect(
        host=os.getenv('DB_HOST', 'localhost'),
        port=int(os.getenv('DB_PORT', 5432)),
        database=os.getenv('DB_NAME', 'alex12060'),
        user=os.getenv('DB_USER', 'alex12060_user'),
        password=os.getenv('DB_PASSWORD', 'alex12060_pass')
    )
    print("✓ Connected to PostgreSQL")

    # Connect to Google Sheets
    scopes = ['https://www.googleapis.com/auth/spreadsheets']
    creds = Credentials.from_service_account_file(
        os.getenv('GOOGLE_SA_JSON', 'google_sheets_credentials.json'),
        scopes=scopes
    )
    sheets_client = gspread.authorize(creds)
    spreadsheet = sheets_client.open_by_key(os.getenv('SPREADSHEET_ID'))
    print("✓ Connected to Google Sheets")

    # Initialize processors
    processors = {
        'shifts': ShiftSyncProcessor(spreadsheet, db_conn),
        'active_bonuses': BonusSyncProcessor(spreadsheet, db_conn),
        'employee_ranks': RankSyncProcessor(spreadsheet, db_conn),
        'employees': EmployeeSyncProcessor(spreadsheet, db_conn),
        'employee_fortnights': FortnightSyncProcessor(spreadsheet, db_conn),
    }

    # Get pending syncs
    with db_conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("""
            SELECT id, table_name, record_id, operation, data, created_at
            FROM sync_queue
            WHERE status = 'pending'
            ORDER BY created_at ASC
            LIMIT 100
        """)
        pending = cur.fetchall()

    print(f"\nFound {len(pending)} pending sync records")

    if not pending:
        print("Nothing to sync!")
        return 0

    synced = 0
    failed = 0

    for record in pending:
        table_name = record['table_name']
        record_id = record['record_id']
        operation = record['operation']
        data = record['data']

        try:
            processor = processors.get(table_name)
            if processor:
                processor.process(record_id, operation, data)

                # Mark as completed
                with db_conn.cursor() as cur:
                    cur.execute("""
                        UPDATE sync_queue
                        SET status = 'completed', processed_at = NOW()
                        WHERE id = %s
                    """, (record['id'],))
                db_conn.commit()

                synced += 1
                print(f"  ✓ {table_name} #{record_id} ({operation})")
            else:
                print(f"  ? Unknown table: {table_name}")

        except Exception as e:
            failed += 1
            error_msg = str(e).split('\n')[0][:100]
            print(f"  ✗ {table_name} #{record_id}: {error_msg}")

            # Rollback failed transaction
            db_conn.rollback()

            # Mark as failed
            try:
                with db_conn.cursor() as cur:
                    cur.execute("""
                        UPDATE sync_queue
                        SET status = 'failed', error_message = %s, processed_at = NOW()
                        WHERE id = %s
                    """, (str(e)[:500], record['id']))
                db_conn.commit()
            except:
                db_conn.rollback()

    print(f"\n" + "=" * 60)
    print(f"✅ Synced: {synced}, ❌ Failed: {failed}")
    print("=" * 60)

    db_conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
