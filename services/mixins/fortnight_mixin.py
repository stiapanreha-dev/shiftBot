"""Fortnight management methods for PostgresService."""

import logging
from typing import Dict, List
from decimal import Decimal
from datetime import date, timedelta

logger = logging.getLogger(__name__)


class FortnightMixin:
    """Fortnight CRUD and totals calculations."""

    def get_fortnight_number(self, day: int) -> int:
        """Get fortnight number from day of month."""
        return 1 if day <= 15 else 2

    def get_fortnight_payment_date(self, year: int, month: int, fortnight: int) -> date:
        """Get payment date for a fortnight."""
        if fortnight == 1:
            return date(year, month, 16)
        else:
            if month == 12:
                return date(year + 1, 1, 1)
            else:
                return date(year, month + 1, 1)

    def update_fortnight_totals_for_date(self, employee_id: int, d: date) -> Dict:
        """Recalculate totals of the fortnight that contains the given date."""
        return self.update_fortnight_totals(
            employee_id, d.year, d.month, self.get_fortnight_number(d.day)
        )

    def get_or_create_fortnight(self, employee_id: int, year: int, month: int, fortnight: int) -> Dict:
        """Get or create fortnight record for employee."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            cursor.execute("""
                SELECT * FROM employee_fortnights
                WHERE employee_id = %s AND year = %s AND month = %s AND fortnight = %s
            """, (employee_id, year, month, fortnight))

            record = cursor.fetchone()
            if record:
                return dict(record)

            payment_date = self.get_fortnight_payment_date(year, month, fortnight)
            cursor.execute("""
                INSERT INTO employee_fortnights (
                    employee_id, year, month, fortnight, payment_date
                ) VALUES (%s, %s, %s, %s, %s)
                RETURNING *
            """, (employee_id, year, month, fortnight, payment_date))

            new_record = cursor.fetchone()
            conn.commit()
            logger.info(f"Created fortnight record: employee={employee_id}, {year}-{month:02d} F{fortnight}")
            return dict(new_record)
        finally:
            cursor.close()
            self._put_conn(conn)

    def update_fortnight_totals(self, employee_id: int, year: int, month: int, fortnight: int) -> Dict:
        """Recalculate fortnight totals from shifts."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            if fortnight == 1:
                start_day, end_day = 1, 15
            else:
                start_day, end_day = 16, 31

            start_date = date(year, month, start_day)
            if fortnight == 2:
                if month == 12:
                    end_date = date(year + 1, 1, 1) - timedelta(days=1)
                else:
                    end_date = date(year, month + 1, 1) - timedelta(days=1)
            else:
                end_date = date(year, month, end_day)

            cursor.execute("""
                SELECT
                    COUNT(*) as total_shifts,
                    COALESCE(SUM(worked_hours), 0) as total_worked_hours,
                    COALESCE(SUM(total_sales), 0) as total_sales,
                    COALESCE(SUM(commissions), 0) as total_commissions,
                    COALESCE(SUM(total_hourly), 0) as total_hourly_pay,
                    COALESCE(SUM(total_made), 0) as total_made,
                    COUNT(*) FILTER (WHERE bonus_counter = TRUE) as bonus_counter_true_count
                FROM shifts
                WHERE employee_id = %s
                  AND date >= %s
                  AND date <= %s
            """, (employee_id, start_date, end_date))

            stats = cursor.fetchone()

            cursor.execute("""
                SELECT setting_value FROM bonus_settings
                WHERE setting_key = 'bonus_counter_percentage' AND is_active = TRUE
            """)
            bonus_setting = cursor.fetchone()
            bonus_pct = Decimal(str(bonus_setting['setting_value'])) if bonus_setting else Decimal('0.01')

            bonus_count = stats['bonus_counter_true_count'] or 0
            total_commissions = Decimal(str(stats['total_commissions']))
            bonus_amount = bonus_count * total_commissions * bonus_pct

            total_made = Decimal(str(stats['total_made']))
            total_salary = total_made + bonus_amount

            payment_date = self.get_fortnight_payment_date(year, month, fortnight)

            cursor.execute("""
                INSERT INTO employee_fortnights (
                    employee_id, year, month, fortnight,
                    total_shifts, total_worked_hours, total_sales,
                    total_commissions, total_hourly_pay, total_made,
                    bonus_counter_true_count, bonus_amount, total_salary,
                    payment_date
                ) VALUES (
                    %s, %s, %s, %s,
                    %s, %s, %s,
                    %s, %s, %s,
                    %s, %s, %s,
                    %s
                )
                ON CONFLICT (employee_id, year, month, fortnight) DO UPDATE SET
                    total_shifts = EXCLUDED.total_shifts,
                    total_worked_hours = EXCLUDED.total_worked_hours,
                    total_sales = EXCLUDED.total_sales,
                    total_commissions = EXCLUDED.total_commissions,
                    total_hourly_pay = EXCLUDED.total_hourly_pay,
                    total_made = EXCLUDED.total_made,
                    bonus_counter_true_count = EXCLUDED.bonus_counter_true_count,
                    bonus_amount = EXCLUDED.bonus_amount,
                    total_salary = EXCLUDED.total_salary,
                    updated_at = now()
                RETURNING *
            """, (
                employee_id, year, month, fortnight,
                stats['total_shifts'], stats['total_worked_hours'], stats['total_sales'],
                stats['total_commissions'], stats['total_hourly_pay'], stats['total_made'],
                bonus_count, bonus_amount, total_salary,
                payment_date
            ))

            updated = cursor.fetchone()
            conn.commit()
            logger.info(f"Updated fortnight totals: employee={employee_id}, {year}-{month:02d} F{fortnight}, salary=${total_salary:.2f}")
            return dict(updated)
        finally:
            cursor.close()
            self._put_conn(conn)

    def get_employee_fortnights(self, employee_id: int, year: int = None, month: int = None) -> List[Dict]:
        """Get fortnight history for employee."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            if year and month:
                cursor.execute("""
                    SELECT * FROM employee_fortnights
                    WHERE employee_id = %s AND year = %s AND month = %s
                    ORDER BY fortnight
                """, (employee_id, year, month))
            elif year:
                cursor.execute("""
                    SELECT * FROM employee_fortnights
                    WHERE employee_id = %s AND year = %s
                    ORDER BY month, fortnight
                """, (employee_id, year))
            else:
                cursor.execute("""
                    SELECT * FROM employee_fortnights
                    WHERE employee_id = %s
                    ORDER BY year DESC, month DESC, fortnight DESC
                """, (employee_id,))

            return [dict(r) for r in cursor.fetchall()]
        finally:
            cursor.close()
            self._put_conn(conn)
