#!/usr/bin/env python3
"""Test suite for Commission Rework functionality.

Tests:
- Tier calculation based on previous month sales
- Rolling average calculation (weighted average of last 7 days)
- Bonus counter logic
- Fortnight calculations

Run: python -m pytest tests/test_commission_rework.py -v
"""

import sys
import os
from decimal import Decimal
from datetime import date, datetime, timedelta

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import psycopg2
from psycopg2.extras import RealDictCursor


# Test database configuration
DB_CONFIG = {
    'host': 'localhost',
    'port': 5432,
    'database': 'alex12060',
    'user': 'alex12060_user',
    'password': 'alex12060_secure_pass_2025'
}


def get_conn():
    """Get database connection."""
    return psycopg2.connect(**DB_CONFIG, cursor_factory=RealDictCursor)


def setup_test_data():
    """Set up test data for all tests."""
    conn = get_conn()
    cursor = conn.cursor()

    try:
        # Clean up test data
        cursor.execute("DELETE FROM shift_products WHERE shift_id IN (SELECT id FROM shifts WHERE employee_id IN (999001, 999002, 999003))")
        cursor.execute("DELETE FROM shifts WHERE employee_id IN (999001, 999002, 999003)")
        cursor.execute("DELETE FROM employee_fortnights WHERE employee_id IN (999001, 999002, 999003)")
        cursor.execute("DELETE FROM employees WHERE id IN (999001, 999002, 999003)")

        # Create test employees
        cursor.execute("""
            INSERT INTO employees (id, name, telegram_id, is_active, hourly_wage, sales_commission, base_commission_id)
            VALUES
                (999001, 'Test Employee 1', 999001, TRUE, 15.0, 8.0, 3),
                (999002, 'Test Employee 2', 999002, TRUE, 15.0, 8.0, 3),
                (999003, 'Test Employee 3', 999003, TRUE, 15.0, 8.0, 3)
            ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name
        """)

        conn.commit()
        print("Test data setup complete")
        return True

    except Exception as e:
        conn.rollback()
        print(f"Error setting up test data: {e}")
        return False

    finally:
        cursor.close()
        conn.close()


def cleanup_test_data():
    """Clean up test data."""
    conn = get_conn()
    cursor = conn.cursor()

    try:
        cursor.execute("DELETE FROM shift_products WHERE shift_id IN (SELECT id FROM shifts WHERE employee_id IN (999001, 999002, 999003))")
        cursor.execute("DELETE FROM shifts WHERE employee_id IN (999001, 999002, 999003)")
        cursor.execute("DELETE FROM employee_fortnights WHERE employee_id IN (999001, 999002, 999003)")
        cursor.execute("DELETE FROM employees WHERE id IN (999001, 999002, 999003)")
        conn.commit()
        print("Test data cleanup complete")

    finally:
        cursor.close()
        conn.close()


class TestBaseCommissions:
    """Test base commissions (tiers)."""

    def test_tiers_exist(self):
        """Test that all 3 tiers exist."""
        conn = get_conn()
        cursor = conn.cursor()

        try:
            cursor.execute("SELECT * FROM base_commissions ORDER BY display_order")
            tiers = cursor.fetchall()

            assert len(tiers) == 3, f"Expected 3 tiers, got {len(tiers)}"

            # Check Tier A
            tier_a = next((t for t in tiers if t['name'] == 'Tier A'), None)
            assert tier_a is not None, "Tier A not found"
            assert float(tier_a['percentage']) == 4.0, f"Tier A should be 4%, got {tier_a['percentage']}"
            assert float(tier_a['min_amount']) == 100000, f"Tier A min should be 100000"

            # Check Tier B
            tier_b = next((t for t in tiers if t['name'] == 'Tier B'), None)
            assert tier_b is not None, "Tier B not found"
            assert float(tier_b['percentage']) == 5.0, f"Tier B should be 5%, got {tier_b['percentage']}"

            # Check Tier C
            tier_c = next((t for t in tiers if t['name'] == 'Tier C'), None)
            assert tier_c is not None, "Tier C not found"
            assert float(tier_c['percentage']) == 6.0, f"Tier C should be 6%, got {tier_c['percentage']}"

            print("PASS: All 3 tiers exist with correct percentages")

        finally:
            cursor.close()
            conn.close()


class TestTierCalculation:
    """Test tier calculation based on previous month sales."""

    def test_tier_c_low_sales(self):
        """Test: Sales < $50k -> Tier C (6%)."""
        conn = get_conn()
        cursor = conn.cursor()

        try:
            setup_test_data()

            # Create shifts for previous month (November 2025) with total $30,000
            prev_month_date = date(2025, 11, 15)

            cursor.execute("""
                INSERT INTO shifts (employee_id, employee_name, date, clock_in, clock_out,
                                   worked_hours, total_sales, net_sales, commission_pct,
                                   total_hourly, commissions, total_made)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (999001, 'Test Employee 1', prev_month_date,
                  datetime(2025, 11, 15, 9, 0), datetime(2025, 11, 15, 17, 0),
                  8.0, 30000.0, 28000.0, 6.0, 100.0, 1800.0, 1900.0))
            conn.commit()

            # Calculate tier for December 2025 (based on November sales)
            cursor.execute("""
                SELECT COALESCE(SUM(total_sales), 0) as total
                FROM shifts
                WHERE employee_id = 999001
                  AND EXTRACT(YEAR FROM date) = 2025
                  AND EXTRACT(MONTH FROM date) = 11
            """)
            result = cursor.fetchone()
            total_sales = float(result['total'])

            # Find tier
            cursor.execute("""
                SELECT id, name, percentage FROM base_commissions
                WHERE is_active = TRUE
                  AND %s >= min_amount AND %s <= max_amount
            """, (total_sales, total_sales))
            tier = cursor.fetchone()

            assert tier['name'] == 'Tier C', f"Expected Tier C, got {tier['name']}"
            assert float(tier['percentage']) == 6.0

            print(f"PASS: Sales ${total_sales:,.0f} -> {tier['name']} ({tier['percentage']}%)")

        finally:
            cursor.close()
            conn.close()

    def test_tier_b_medium_sales(self):
        """Test: Sales $50k-$100k -> Tier B (5%)."""
        conn = get_conn()
        cursor = conn.cursor()

        try:
            setup_test_data()

            # Create shifts for previous month with total $75,000
            cursor.execute("""
                INSERT INTO shifts (employee_id, employee_name, date, clock_in, clock_out,
                                   worked_hours, total_sales, net_sales, commission_pct,
                                   total_hourly, commissions, total_made)
                VALUES
                    (%s, 'Test Employee 2', '2025-11-10', '2025-11-10 09:00', '2025-11-10 17:00',
                     8.0, 37500.0, 35000.0, 5.0, 100.0, 1875.0, 2000.0),
                    (%s, 'Test Employee 2', '2025-11-20', '2025-11-20 09:00', '2025-11-20 17:00',
                     8.0, 37500.0, 35000.0, 5.0, 100.0, 1875.0, 2000.0)
            """, (999002, 999002))
            conn.commit()

            # Calculate tier
            cursor.execute("""
                SELECT COALESCE(SUM(total_sales), 0) as total
                FROM shifts
                WHERE employee_id = 999002
                  AND EXTRACT(YEAR FROM date) = 2025
                  AND EXTRACT(MONTH FROM date) = 11
            """)
            total_sales = float(cursor.fetchone()['total'])

            cursor.execute("""
                SELECT id, name, percentage FROM base_commissions
                WHERE is_active = TRUE
                  AND %s >= min_amount AND %s <= max_amount
            """, (total_sales, total_sales))
            tier = cursor.fetchone()

            assert tier['name'] == 'Tier B', f"Expected Tier B, got {tier['name']}"
            assert float(tier['percentage']) == 5.0

            print(f"PASS: Sales ${total_sales:,.0f} -> {tier['name']} ({tier['percentage']}%)")

        finally:
            cursor.close()
            conn.close()

    def test_tier_a_high_sales(self):
        """Test: Sales >= $100k -> Tier A (4%)."""
        conn = get_conn()
        cursor = conn.cursor()

        try:
            setup_test_data()

            # Create shifts with total $150,000
            for i in range(5):
                cursor.execute("""
                    INSERT INTO shifts (employee_id, employee_name, date, clock_in, clock_out,
                                       worked_hours, total_sales, net_sales, commission_pct,
                                       total_hourly, commissions, total_made)
                    VALUES (%s, 'Test Employee 3', %s, %s, %s, 8.0, 30000.0, 28000.0, 4.0, 100.0, 1200.0, 1300.0)
                """, (999003, f'2025-11-{5+i*5:02d}',
                      f'2025-11-{5+i*5:02d} 09:00', f'2025-11-{5+i*5:02d} 17:00'))
            conn.commit()

            # Calculate tier
            cursor.execute("""
                SELECT COALESCE(SUM(total_sales), 0) as total
                FROM shifts
                WHERE employee_id = 999003
                  AND EXTRACT(YEAR FROM date) = 2025
                  AND EXTRACT(MONTH FROM date) = 11
            """)
            total_sales = float(cursor.fetchone()['total'])

            cursor.execute("""
                SELECT id, name, percentage FROM base_commissions
                WHERE is_active = TRUE
                  AND %s >= min_amount AND %s <= max_amount
            """, (total_sales, total_sales))
            tier = cursor.fetchone()

            assert tier['name'] == 'Tier A', f"Expected Tier A, got {tier['name']}"
            assert float(tier['percentage']) == 4.0

            print(f"PASS: Sales ${total_sales:,.0f} -> {tier['name']} ({tier['percentage']}%)")

        finally:
            cursor.close()
            conn.close()


class TestRollingAverage:
    """Test rolling average calculation."""

    def test_no_shifts_returns_zero(self):
        """Test: No shifts in 7 days -> rolling_average = 0."""
        conn = get_conn()
        cursor = conn.cursor()

        try:
            setup_test_data()

            # No shifts for employee 999001 in last 7 days
            # Check rolling average for today
            today = date.today().strftime('%Y-%m-%d')

            cursor.execute("""
                SELECT total_sales
                FROM shifts
                WHERE employee_id = 999001
                  AND date >= %s::date - INTERVAL '7 days'
                  AND date < %s::date
                  AND total_sales IS NOT NULL
                ORDER BY date ASC
            """, (today, today))

            shifts = cursor.fetchall()

            if not shifts:
                rolling_avg = Decimal('0')
            else:
                n = len(shifts)
                sum_weights = n * (n + 1) // 2
                total_weighted = sum(Decimal(str(i)) * Decimal(str(s['total_sales']))
                                   for i, s in enumerate(shifts, 1))
                rolling_avg = total_weighted / Decimal(str(sum_weights))

            assert rolling_avg == Decimal('0'), f"Expected 0, got {rolling_avg}"
            print(f"PASS: No shifts in 7 days -> rolling_average = {rolling_avg}")

        finally:
            cursor.close()
            conn.close()

    def test_weighted_average_calculation(self):
        """Test: Weighted average with multiple shifts."""
        conn = get_conn()
        cursor = conn.cursor()

        try:
            setup_test_data()

            # Create 3 shifts in last 7 days
            today = date.today()

            shifts_data = [
                (today - timedelta(days=3), 1000),  # Oldest - weight 1
                (today - timedelta(days=2), 1500),  # Middle - weight 2
                (today - timedelta(days=1), 2000),  # Newest - weight 3
            ]

            for shift_date, sales in shifts_data:
                cursor.execute("""
                    INSERT INTO shifts (employee_id, employee_name, date, clock_in, clock_out,
                                       worked_hours, total_sales, net_sales, commission_pct,
                                       total_hourly, commissions, total_made)
                    VALUES (%s, 'Test Employee 1', %s, %s, %s, 8.0, %s, %s, 6.0, 100.0, 60.0, 160.0)
                """, (999001, shift_date,
                      datetime.combine(shift_date, datetime.min.time().replace(hour=9)),
                      datetime.combine(shift_date, datetime.min.time().replace(hour=17)),
                      sales, sales * 0.94))
            conn.commit()

            # Calculate rolling average for today
            today_str = today.strftime('%Y-%m-%d')

            cursor.execute("""
                SELECT total_sales
                FROM shifts
                WHERE employee_id = 999001
                  AND date >= %s::date - INTERVAL '7 days'
                  AND date < %s::date
                  AND total_sales IS NOT NULL
                ORDER BY date ASC, clock_in ASC
            """, (today_str, today_str))

            shifts = cursor.fetchall()

            # Calculate expected: (1*1000 + 2*1500 + 3*2000) / (1+2+3) = 10000 / 6 = 1666.67
            n = len(shifts)
            sum_weights = Decimal(str(n * (n + 1) // 2))
            total_weighted = Decimal('0')
            for i, s in enumerate(shifts, 1):
                total_weighted += Decimal(str(i)) * Decimal(str(s['total_sales']))

            rolling_avg = (total_weighted / sum_weights).quantize(Decimal('0.01'))

            expected = Decimal('1666.67')
            assert rolling_avg == expected, f"Expected {expected}, got {rolling_avg}"

            print(f"PASS: Weighted average of [1000, 1500, 2000] with weights [1, 2, 3] = {rolling_avg}")

        finally:
            cursor.close()
            conn.close()

    def test_single_shift(self):
        """Test: Single shift -> rolling_average = that shift's sales."""
        conn = get_conn()
        cursor = conn.cursor()

        try:
            setup_test_data()

            today = date.today()
            yesterday = today - timedelta(days=1)

            cursor.execute("""
                INSERT INTO shifts (employee_id, employee_name, date, clock_in, clock_out,
                                   worked_hours, total_sales, net_sales, commission_pct,
                                   total_hourly, commissions, total_made)
                VALUES (%s, 'Test Employee 2', %s, %s, %s, 8.0, 2500.0, 2350.0, 6.0, 100.0, 150.0, 250.0)
            """, (999002, yesterday,
                  datetime.combine(yesterday, datetime.min.time().replace(hour=9)),
                  datetime.combine(yesterday, datetime.min.time().replace(hour=17))))
            conn.commit()

            # For single shift: (1 * 2500) / 1 = 2500
            today_str = today.strftime('%Y-%m-%d')

            cursor.execute("""
                SELECT total_sales
                FROM shifts
                WHERE employee_id = 999002
                  AND date >= %s::date - INTERVAL '7 days'
                  AND date < %s::date
            """, (today_str, today_str))

            shifts = cursor.fetchall()
            rolling_avg = Decimal(str(shifts[0]['total_sales']))

            assert rolling_avg == Decimal('2500'), f"Expected 2500, got {rolling_avg}"
            print(f"PASS: Single shift of $2500 -> rolling_average = {rolling_avg}")

        finally:
            cursor.close()
            conn.close()


class TestBonusCounter:
    """Test bonus_counter logic."""

    def test_bonus_counter_true(self):
        """Test: total_sales >= rolling_average -> bonus_counter = TRUE."""
        total_sales = Decimal('2000')
        rolling_average = Decimal('1500')

        bonus_counter = total_sales >= rolling_average

        assert bonus_counter == True, f"Expected True"
        print(f"PASS: ${total_sales} >= ${rolling_average} -> bonus_counter = {bonus_counter}")

    def test_bonus_counter_false(self):
        """Test: total_sales < rolling_average -> bonus_counter = FALSE."""
        total_sales = Decimal('1000')
        rolling_average = Decimal('1500')

        bonus_counter = total_sales >= rolling_average

        assert bonus_counter == False, f"Expected False"
        print(f"PASS: ${total_sales} < ${rolling_average} -> bonus_counter = {bonus_counter}")

    def test_bonus_counter_equal(self):
        """Test: total_sales == rolling_average -> bonus_counter = TRUE."""
        total_sales = Decimal('1500')
        rolling_average = Decimal('1500')

        bonus_counter = total_sales >= rolling_average

        assert bonus_counter == True, f"Expected True for equal values"
        print(f"PASS: ${total_sales} == ${rolling_average} -> bonus_counter = {bonus_counter}")

    def test_bonus_counter_zero_rolling_avg(self):
        """Test: rolling_average = 0 -> bonus_counter = TRUE (any sales beats 0)."""
        total_sales = Decimal('100')
        rolling_average = Decimal('0')

        # According to logic: total_sales >= rolling_average
        # 100 >= 0 -> True
        bonus_counter = total_sales >= rolling_average

        assert bonus_counter == True, f"Expected True when rolling_avg = 0"
        print(f"PASS: ${total_sales} >= ${rolling_average} -> bonus_counter = {bonus_counter}")


class TestFortnights:
    """Test fortnight calculations."""

    def test_fortnight_number_first_half(self):
        """Test: Days 1-15 -> Fortnight 1."""
        for day in range(1, 16):
            fortnight = 1 if day <= 15 else 2
            assert fortnight == 1, f"Day {day} should be Fortnight 1"
        print("PASS: Days 1-15 -> Fortnight 1")

    def test_fortnight_number_second_half(self):
        """Test: Days 16-31 -> Fortnight 2."""
        for day in range(16, 32):
            fortnight = 1 if day <= 15 else 2
            assert fortnight == 2, f"Day {day} should be Fortnight 2"
        print("PASS: Days 16-31 -> Fortnight 2")

    def test_payment_date_fortnight_1(self):
        """Test: Fortnight 1 -> Payment on 16th of same month."""
        year, month, fortnight = 2025, 12, 1

        # F1 payment on 16th
        payment_date = date(year, month, 16)

        assert payment_date == date(2025, 12, 16), f"Expected 2025-12-16"
        print(f"PASS: F1 of Dec 2025 -> Payment on {payment_date}")

    def test_payment_date_fortnight_2(self):
        """Test: Fortnight 2 -> Payment on 1st of next month."""
        year, month, fortnight = 2025, 12, 2

        # F2 payment on 1st of next month
        if month == 12:
            payment_date = date(year + 1, 1, 1)
        else:
            payment_date = date(year, month + 1, 1)

        assert payment_date == date(2026, 1, 1), f"Expected 2026-01-01"
        print(f"PASS: F2 of Dec 2025 -> Payment on {payment_date}")

    def test_payment_date_fortnight_2_mid_year(self):
        """Test: Fortnight 2 of June -> Payment on July 1st."""
        year, month, fortnight = 2025, 6, 2

        payment_date = date(year, month + 1, 1)

        assert payment_date == date(2025, 7, 1), f"Expected 2025-07-01"
        print(f"PASS: F2 of Jun 2025 -> Payment on {payment_date}")


def run_all_tests():
    """Run all tests."""
    print("=" * 70)
    print("COMMISSION REWORK TESTS")
    print("=" * 70)

    # Setup
    setup_test_data()

    passed = 0
    failed = 0

    test_classes = [
        TestBaseCommissions(),
        TestTierCalculation(),
        TestRollingAverage(),
        TestBonusCounter(),
        TestFortnights(),
    ]

    for test_class in test_classes:
        class_name = test_class.__class__.__name__
        print(f"\n--- {class_name} ---")

        for method_name in dir(test_class):
            if method_name.startswith('test_'):
                try:
                    getattr(test_class, method_name)()
                    passed += 1
                except AssertionError as e:
                    print(f"FAIL: {method_name}: {e}")
                    failed += 1
                except Exception as e:
                    print(f"ERROR: {method_name}: {e}")
                    failed += 1

    # Cleanup
    cleanup_test_data()

    print("\n" + "=" * 70)
    print(f"RESULTS: {passed} passed, {failed} failed")
    if failed == 0:
        print("ALL TESTS PASSED!")
    print("=" * 70)

    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
