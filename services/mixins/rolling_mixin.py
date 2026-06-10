"""Rolling average and bonus counter methods for PostgresService."""

import logging
from typing import Optional
from decimal import Decimal

from services.formatters import DateFormatter

logger = logging.getLogger(__name__)


class RollingMixin:
    """Rolling average, bonus counter, and tomorrow target calculations."""

    @staticmethod
    def weighted_average(sales: list) -> Decimal:
        """Weighted average where the i-th value (1 = oldest) has weight i.

        Formula: Σ(i × sales_i) / Σ(1..N). Example for [100, 200, 300]:
        (1×100 + 2×200 + 3×300) / 6 = 233.33
        """
        if not sales:
            return Decimal('0')
        n = len(sales)
        sum_of_weights = Decimal(n * (n + 1) // 2)
        total_weighted = sum(
            Decimal(str(i)) * Decimal(str(s)) for i, s in enumerate(sales, start=1)
        )
        return (total_weighted / sum_of_weights).quantize(Decimal('0.01'))

    def calculate_rolling_average(self, employee_id: int, shift_date: str) -> Decimal:
        """Calculate weighted rolling average of total_sales for last 7 SHIFTS."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            shift_date_clean = DateFormatter.to_db_date(shift_date)
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
            """, (employee_id, shift_date_clean))

            shifts = cursor.fetchall()
            return self.weighted_average([s['total_sales'] for s in shifts])
        finally:
            cursor.close()
            self._put_conn(conn)

    def calculate_bonus_counter(self, total_sales: Decimal, rolling_average: Optional[Decimal]) -> bool:
        """Determine if bonus_counter should be True."""
        if rolling_average is None:
            return False
        return Decimal(str(total_sales)) >= rolling_average

    def calculate_tomorrow_target(self, employee_id: int, today_date: str) -> Decimal:
        """Calculate rolling average target for tomorrow (including today's shift)."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            today_clean = DateFormatter.to_db_date(today_date)
            cursor.execute("""
                SELECT total_sales FROM (
                    SELECT total_sales, date, clock_in
                    FROM shifts
                    WHERE employee_id = %s
                      AND date <= %s::date
                      AND total_sales IS NOT NULL
                    ORDER BY date DESC, clock_in DESC
                    LIMIT 7
                ) sub
                ORDER BY date ASC, clock_in ASC
            """, (employee_id, today_clean))

            shifts = cursor.fetchall()
            return self.weighted_average([s['total_sales'] for s in shifts])
        finally:
            cursor.close()
            self._put_conn(conn)

    def get_fortnight_bonus_count(self, employee_id: int, year: int = None, month: int = None, fortnight: int = None) -> int:
        """Get count of bonus_counter=TRUE for current fortnight."""
        from datetime import date as date_class

        if year is None or month is None or fortnight is None:
            today = date_class.today()
            year = today.year
            month = today.month
            fortnight = self.get_fortnight_number(today.day)

        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            if fortnight == 1:
                start_day, end_day = 1, 15
            else:
                start_day = 16
                if month in [1, 3, 5, 7, 8, 10, 12]:
                    end_day = 31
                elif month in [4, 6, 9, 11]:
                    end_day = 30
                elif month == 2:
                    if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0):
                        end_day = 29
                    else:
                        end_day = 28

            cursor.execute("""
                SELECT COUNT(*) as bonus_count
                FROM shifts
                WHERE employee_id = %s
                  AND EXTRACT(YEAR FROM date) = %s
                  AND EXTRACT(MONTH FROM date) = %s
                  AND EXTRACT(DAY FROM date) >= %s
                  AND EXTRACT(DAY FROM date) <= %s
                  AND bonus_counter = TRUE
            """, (employee_id, year, month, start_day, end_day))

            result = cursor.fetchone()
            return result['bonus_count'] if result else 0
        finally:
            cursor.close()
            self._put_conn(conn)
