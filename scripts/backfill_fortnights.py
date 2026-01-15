#!/usr/bin/env python3
"""Backfill employee_fortnights from existing shifts."""

import os
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Load .env
env_path = project_root / '.env'
if env_path.exists():
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                os.environ[key] = value

from services.postgres_service import PostgresService


def main():
    ps = PostgresService()
    conn = ps._get_conn()
    cursor = conn.cursor()

    # Get unique (employee_id, year, month, fortnight) from shifts
    cursor.execute("""
        SELECT DISTINCT
            employee_id,
            EXTRACT(YEAR FROM date)::int as year,
            EXTRACT(MONTH FROM date)::int as month,
            CASE WHEN EXTRACT(DAY FROM date) <= 15 THEN 1 ELSE 2 END as fortnight
        FROM shifts
        WHERE employee_id IS NOT NULL AND date IS NOT NULL
        ORDER BY year, month, fortnight, employee_id
    """)

    combinations = cursor.fetchall()
    print(f"Found {len(combinations)} unique (employee, year, month, fortnight) combinations")

    success = 0
    failed = 0

    for i, row in enumerate(combinations):
        emp_id = int(row['employee_id'])
        year = int(row['year'])
        month = int(row['month'])
        fortnight = int(row['fortnight'])
        try:
            ps.update_fortnight_totals(emp_id, year, month, fortnight)
            print(f"[{i+1}/{len(combinations)}] Updated: employee={emp_id}, {year}-{month:02d} F{fortnight}")
            success += 1
        except Exception as e:
            print(f"[{i+1}/{len(combinations)}] FAILED: employee={emp_id}, {year}-{month:02d} F{fortnight}: {e}")
            failed += 1

    cursor.close()
    conn.close()

    print(f"\nDone! Success: {success}, Failed: {failed}")


if __name__ == "__main__":
    main()
