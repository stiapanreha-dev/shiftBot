#!/usr/bin/env python3
"""Recalculate rolling_average, bonus_counter, and employee_fortnights.

This script recalculates commission data for all shifts and updates
employee_fortnights table with correct totals.

Usage:
    python scripts/recalculate_commission_data.py
"""

import sys
import os
from decimal import Decimal
from datetime import datetime

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.postgres_service import PostgresService


def recalculate_all():
    """Recalculate all commission data."""
    service = PostgresService()

    print("=" * 70)
    print("COMMISSION DATA RECALCULATION")
    print("=" * 70)

    # Step 1: Get all shifts ordered by date
    print("\n[Step 1] Recalculating rolling_average and bonus_counter for all shifts...")

    conn = service._get_conn()
    cursor = conn.cursor()

    try:
        # Get all shifts ordered by employee and date
        cursor.execute("""
            SELECT id, employee_id, date, total_sales, clock_in
            FROM shifts
            ORDER BY employee_id, date, clock_in
        """)
        shifts = cursor.fetchall()

        print(f"  Found {len(shifts)} shifts to process")

        updated_count = 0
        bonus_true_count = 0

        for shift in shifts:
            shift_id = shift['id']
            employee_id = shift['employee_id']
            shift_date = shift['date'].strftime('%Y-%m-%d')
            total_sales = Decimal(str(shift['total_sales'])) if shift['total_sales'] else Decimal('0')

            # Calculate rolling average
            rolling_avg = service.calculate_rolling_average(employee_id, shift_date)

            # Calculate bonus counter
            bonus_counter = service.calculate_bonus_counter(total_sales, rolling_avg)

            if bonus_counter:
                bonus_true_count += 1

            # Update shift
            cursor.execute("""
                UPDATE shifts
                SET rolling_average = %s, bonus_counter = %s
                WHERE id = %s
            """, (rolling_avg, bonus_counter, shift_id))

            updated_count += 1

            if updated_count % 10 == 0:
                print(f"    Processed {updated_count}/{len(shifts)} shifts...")

        conn.commit()
        print(f"  Updated {updated_count} shifts")
        print(f"  bonus_counter=TRUE: {bonus_true_count}, FALSE: {updated_count - bonus_true_count}")

        # Step 2: Update employee_fortnights
        print("\n[Step 2] Updating employee_fortnights...")

        # Get unique (employee_id, year, month, fortnight) combinations
        cursor.execute("""
            SELECT DISTINCT
                employee_id,
                EXTRACT(YEAR FROM date)::int as year,
                EXTRACT(MONTH FROM date)::int as month,
                CASE WHEN EXTRACT(DAY FROM date) <= 15 THEN 1 ELSE 2 END as fortnight
            FROM shifts
            ORDER BY employee_id, year, month, fortnight
        """)
        periods = cursor.fetchall()

        print(f"  Found {len(periods)} fortnight periods to update")

        for period in periods:
            employee_id = period['employee_id']
            year = period['year']
            month = period['month']
            fortnight = period['fortnight']

            result = service.update_fortnight_totals(employee_id, year, month, fortnight)

            if result:
                print(f"    Employee {employee_id}: {year}-{month:02d} F{fortnight} -> "
                      f"salary=${result['total_salary']:.2f}, bonus_count={result['bonus_counter_true_count']}")

        print("\n[Step 3] Verification...")

        # Verify shifts
        cursor.execute("""
            SELECT
                SUM(CASE WHEN bonus_counter THEN 1 ELSE 0 END) as bonus_true,
                SUM(CASE WHEN NOT bonus_counter THEN 1 ELSE 0 END) as bonus_false
            FROM shifts
        """)
        shift_stats = cursor.fetchone()
        print(f"  Shifts: bonus_counter=TRUE: {shift_stats['bonus_true']}, FALSE: {shift_stats['bonus_false']}")

        # Verify fortnights
        cursor.execute("""
            SELECT COUNT(*) as count, SUM(total_salary) as total
            FROM employee_fortnights
        """)
        fortnight_stats = cursor.fetchone()
        print(f"  Fortnights: {fortnight_stats['count']} records, total_salary=${fortnight_stats['total'] or 0:.2f}")

        print("\n" + "=" * 70)
        print("RECALCULATION COMPLETE!")
        print("=" * 70)

    except Exception as e:
        conn.rollback()
        print(f"ERROR: {e}")
        raise
    finally:
        cursor.close()
        conn.close()


if __name__ == "__main__":
    recalculate_all()
