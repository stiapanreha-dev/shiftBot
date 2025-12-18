#!/usr/bin/env python3
"""Create test shifts using service methods (not raw SQL).

This ensures rolling_average, bonus_counter, and employee_fortnights
are calculated correctly through the actual business logic.

Usage:
    python scripts/create_test_shifts.py
"""

import sys
import os
from datetime import datetime, timedelta
from decimal import Decimal

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.postgres_service import PostgresService
import psycopg2
from psycopg2.extras import RealDictCursor


DB_CONFIG = {
    'host': 'localhost',
    'port': 5432,
    'database': 'alex12060',
    'user': 'alex12060_user',
    'password': 'alex12060_secure_pass_2025'
}


def cleanup_test_data():
    """Remove existing test data."""
    conn = psycopg2.connect(**DB_CONFIG, cursor_factory=RealDictCursor)
    cursor = conn.cursor()

    try:
        print("Cleaning up existing test data...")
        cursor.execute("DELETE FROM employee_fortnights WHERE employee_id >= 1001")
        cursor.execute("DELETE FROM shift_products WHERE shift_id IN (SELECT id FROM shifts WHERE employee_id >= 1001)")
        cursor.execute("DELETE FROM shifts WHERE employee_id >= 1001")
        cursor.execute("DELETE FROM employees WHERE id >= 1001")
        conn.commit()
        print("  Cleanup complete")
    finally:
        cursor.close()
        conn.close()


def create_test_employees():
    """Create test employees."""
    conn = psycopg2.connect(**DB_CONFIG, cursor_factory=RealDictCursor)
    cursor = conn.cursor()

    try:
        print("Creating test employees...")
        cursor.execute("""
            INSERT INTO employees (id, name, telegram_id, is_active, hourly_wage, sales_commission, base_commission_id)
            VALUES
                (2001, 'Test Alice', 2001, TRUE, 15.0, 8.0, 3),
                (2002, 'Test Bob', 2002, TRUE, 15.0, 8.0, 3),
                (2003, 'Test Carol', 2003, TRUE, 15.0, 8.0, 3)
            ON CONFLICT (id) DO NOTHING
        """)
        conn.commit()
        print("  Created 3 test employees (2001, 2002, 2003)")
    finally:
        cursor.close()
        conn.close()


def create_shifts_via_service():
    """Create shifts using PostgresService.create_shift() method."""
    service = PostgresService()

    today = datetime.now().date()

    print("\n" + "=" * 70)
    print("CREATING TEST SHIFTS VIA SERVICE")
    print("=" * 70)

    # Alice (2001): 5 shifts over 5 days - should have rolling_average calculated
    print("\n[Alice - 2001] Creating 5 shifts over 5 days...")
    alice_sales = [1000, 1200, 800, 1500, 1100]  # Varied sales

    for i, sales in enumerate(alice_sales):
        shift_date = (today - timedelta(days=5-i)).strftime('%Y/%m/%d')
        clock_in = f"{shift_date} 09:00:00"
        clock_out = f"{shift_date} 17:00:00"

        shift_data = {
            'employee_id': 2001,
            'employee_name': 'Test Alice',
            'shift_date': shift_date,
            'clock_in': clock_in,
            'clock_out': clock_out,
            'worked_hours': 8.0,
            'model_a': sales * 0.5,  # 50% to Model A
            'model_b': sales * 0.3,  # 30% to Model B
            'model_c': sales * 0.2,  # 20% to Model C
            'total_sales': sales,
            'net_sales': sales * 0.94,
            'commission_pct': 6.0,
        }

        shift_id = service.create_shift(shift_data)
        print(f"    Day {i+1}: shift_id={shift_id}, sales=${sales}")

    # Bob (2002): 2 shifts - should have minimal rolling_average history
    print("\n[Bob - 2002] Creating 2 shifts...")
    bob_sales = [2000, 2500]

    for i, sales in enumerate(bob_sales):
        shift_date = (today - timedelta(days=3-i*2)).strftime('%Y/%m/%d')
        clock_in = f"{shift_date} 10:00:00"
        clock_out = f"{shift_date} 18:00:00"

        shift_data = {
            'employee_id': 2002,
            'employee_name': 'Test Bob',
            'shift_date': shift_date,
            'clock_in': clock_in,
            'clock_out': clock_out,
            'worked_hours': 8.0,
            'model_a': sales * 0.4,
            'model_b': sales * 0.4,
            'model_c': sales * 0.2,
            'total_sales': sales,
            'net_sales': sales * 0.94,
            'commission_pct': 6.0,
        }

        shift_id = service.create_shift(shift_data)
        print(f"    Shift {i+1}: shift_id={shift_id}, sales=${sales}")

    # Carol (2003): 1 shift today - should have rolling_average = 0
    print("\n[Carol - 2003] Creating 1 shift (no history)...")
    shift_date = today.strftime('%Y/%m/%d')
    clock_in = f"{shift_date} 09:00:00"
    clock_out = f"{shift_date} 17:00:00"

    shift_data = {
        'employee_id': 2003,
        'employee_name': 'Test Carol',
        'shift_date': shift_date,
        'clock_in': clock_in,
        'clock_out': clock_out,
        'worked_hours': 8.0,
        'model_a': 600,
        'model_b': 300,
        'model_c': 100,
        'total_sales': 1000,
        'net_sales': 940,
        'commission_pct': 6.0,
    }

    shift_id = service.create_shift(shift_data)
    print(f"    Shift: shift_id={shift_id}, sales=$1000")


def verify_results():
    """Verify the results."""
    conn = psycopg2.connect(**DB_CONFIG, cursor_factory=RealDictCursor)
    cursor = conn.cursor()

    try:
        print("\n" + "=" * 70)
        print("VERIFICATION")
        print("=" * 70)

        # Check shifts with rolling_average and bonus_counter
        print("\n[Shifts with rolling_average and bonus_counter]")
        cursor.execute("""
            SELECT employee_id, employee_name, date::date, total_sales,
                   rolling_average, bonus_counter
            FROM shifts
            WHERE employee_id IN (2001, 2002, 2003)
            ORDER BY employee_id, date
        """)
        shifts = cursor.fetchall()

        for s in shifts:
            bonus = "TRUE" if s['bonus_counter'] else "FALSE"
            comparison = ">=" if s['bonus_counter'] else "<"
            print(f"  {s['employee_name'][:10]:10} | {s['date']} | "
                  f"sales=${s['total_sales']:8.2f} | "
                  f"rolling_avg=${s['rolling_average'] or 0:8.2f} | "
                  f"bonus={bonus:5} ({s['total_sales']:.0f} {comparison} {s['rolling_average'] or 0:.0f})")

        # Check employee_fortnights
        print("\n[Employee Fortnights]")
        cursor.execute("""
            SELECT ef.employee_id, e.name, ef.year, ef.month, ef.fortnight,
                   ef.total_shifts, ef.total_sales, ef.total_made,
                   ef.bonus_counter_true_count, ef.bonus_amount, ef.total_salary
            FROM employee_fortnights ef
            JOIN employees e ON ef.employee_id = e.id
            WHERE ef.employee_id IN (2001, 2002, 2003)
            ORDER BY ef.employee_id, ef.year, ef.month, ef.fortnight
        """)
        fortnights = cursor.fetchall()

        if fortnights:
            for f in fortnights:
                print(f"  {f['name'][:10]:10} | {f['year']}-{f['month']:02d} F{f['fortnight']} | "
                      f"shifts={f['total_shifts']} | sales=${f['total_sales']:.2f} | "
                      f"made=${f['total_made']:.2f} | bonus_count={f['bonus_counter_true_count']} | "
                      f"bonus=${f['bonus_amount']:.2f} | SALARY=${f['total_salary']:.2f}")
        else:
            print("  No fortnight records found!")

        # Summary statistics
        print("\n[Summary]")
        cursor.execute("""
            SELECT
                COUNT(*) as total_shifts,
                SUM(CASE WHEN bonus_counter THEN 1 ELSE 0 END) as bonus_true,
                SUM(CASE WHEN NOT bonus_counter THEN 1 ELSE 0 END) as bonus_false
            FROM shifts
            WHERE employee_id IN (2001, 2002, 2003)
        """)
        stats = cursor.fetchone()
        print(f"  Total shifts: {stats['total_shifts']}")
        print(f"  bonus_counter=TRUE: {stats['bonus_true']}")
        print(f"  bonus_counter=FALSE: {stats['bonus_false']}")

    finally:
        cursor.close()
        conn.close()


def main():
    """Main entry point."""
    cleanup_test_data()
    create_test_employees()
    create_shifts_via_service()
    verify_results()

    print("\n" + "=" * 70)
    print("TEST DATA CREATION COMPLETE!")
    print("=" * 70)


if __name__ == "__main__":
    main()
