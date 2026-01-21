#!/usr/bin/env python3
"""Recalculate rolling_average for all shifts using new logic (7 SHIFTS instead of 7 days).

This script:
1. Gets all shifts ordered by employee_id, date, clock_in
2. For each shift, recalculates rolling_average using last 7 SHIFTS (not days)
3. Updates bonus_counter (total_sales >= rolling_average)
4. Saves changes to database
5. Adds to sync_queue for Google Sheets sync

Usage:
    python3 scripts/recalculate_rolling_average.py [--dry-run]
"""

import sys
import os
from decimal import Decimal
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import psycopg2
from psycopg2 import extras
from config import Config


def get_db_connection():
    """Get PostgreSQL connection."""
    db_params = Config.get_db_params()
    return psycopg2.connect(
        **db_params,
        cursor_factory=extras.RealDictCursor
    )


def calculate_rolling_average_for_shift(cursor, employee_id: int, shift_date, shift_id: int) -> Decimal:
    """Calculate weighted rolling average using last 7 SHIFTS before this shift.

    Args:
        cursor: Database cursor
        employee_id: Employee ID
        shift_date: Date of current shift
        shift_id: ID of current shift (to exclude it)

    Returns:
        Weighted average (0 if no previous shifts)
    """
    # Get last 7 SHIFTS before current shift date, sorted oldest to newest
    cursor.execute("""
        SELECT total_sales FROM (
            SELECT total_sales, date, clock_in
            FROM shifts
            WHERE employee_id = %s
              AND date < %s::date
              AND total_sales IS NOT NULL
            ORDER BY date DESC, clock_in DESC
            LIMIT 7
        ) sub
        ORDER BY date ASC, clock_in ASC
    """, (employee_id, shift_date))

    shifts = cursor.fetchall()

    if not shifts:
        return Decimal('0')

    # Calculate weighted average
    n = len(shifts)
    sum_of_weights = Decimal(str(n * (n + 1) // 2))  # 1 + 2 + ... + N

    total_weighted = Decimal('0')
    for i, shift in enumerate(shifts, start=1):
        weight = Decimal(str(i))
        sales = Decimal(str(shift['total_sales']))
        total_weighted += weight * sales

    rolling_avg = total_weighted / sum_of_weights
    return rolling_avg.quantize(Decimal('0.01'))


def recalculate_all_shifts(dry_run: bool = False):
    """Recalculate rolling_average and bonus_counter for all shifts."""
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # Get all shifts ordered by employee and date
        cursor.execute("""
            SELECT id, employee_id, date, total_sales, rolling_average, bonus_counter
            FROM shifts
            WHERE total_sales IS NOT NULL
            ORDER BY employee_id, date ASC, clock_in ASC
        """)

        shifts = cursor.fetchall()
        print(f"Found {len(shifts)} shifts to process")

        updated_count = 0
        unchanged_count = 0

        for shift in shifts:
            shift_id = shift['id']
            employee_id = shift['employee_id']
            shift_date = shift['date']
            total_sales = Decimal(str(shift['total_sales']))
            old_rolling_avg = Decimal(str(shift['rolling_average'])) if shift['rolling_average'] else Decimal('0')
            old_bonus_counter = shift['bonus_counter']

            # Calculate new rolling_average
            new_rolling_avg = calculate_rolling_average_for_shift(
                cursor, employee_id, shift_date, shift_id
            )

            # Calculate new bonus_counter
            new_bonus_counter = total_sales >= new_rolling_avg if new_rolling_avg > 0 else False

            # Check if changed
            if new_rolling_avg != old_rolling_avg or new_bonus_counter != old_bonus_counter:
                updated_count += 1
                print(f"Shift #{shift_id} ({shift_date}, emp={employee_id}): "
                      f"rolling_avg {old_rolling_avg} → {new_rolling_avg}, "
                      f"bonus_counter {old_bonus_counter} → {new_bonus_counter}")

                if not dry_run:
                    # Update shift
                    cursor.execute("""
                        UPDATE shifts
                        SET rolling_average = %s,
                            bonus_counter = %s,
                            updated_at = NOW()
                        WHERE id = %s
                    """, (new_rolling_avg, new_bonus_counter, shift_id))
            else:
                unchanged_count += 1

        print(f"\n{'[DRY RUN] ' if dry_run else ''}Summary:")
        print(f"  Total shifts: {len(shifts)}")
        print(f"  Updated: {updated_count}")
        print(f"  Unchanged: {unchanged_count}")

        if not dry_run:
            conn.commit()
            print("\n✓ Changes committed to database")
            print("  Note: sync_queue triggers will handle Google Sheets sync")
        else:
            conn.rollback()
            print("\n[DRY RUN] No changes made")

    except Exception as e:
        conn.rollback()
        print(f"Error: {e}")
        raise
    finally:
        cursor.close()
        conn.close()


def main():
    dry_run = '--dry-run' in sys.argv or '-n' in sys.argv

    if dry_run:
        print("=== DRY RUN MODE (no changes will be made) ===\n")
    else:
        print("=== RECALCULATING ROLLING AVERAGE (7 SHIFTS) ===\n")
        response = input("This will update all shifts. Continue? [y/N]: ")
        if response.lower() != 'y':
            print("Aborted.")
            return

    recalculate_all_shifts(dry_run=dry_run)


if __name__ == '__main__':
    main()
