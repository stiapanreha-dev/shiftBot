"""Employee fortnight sync processor."""

from typing import List, Optional, Any

from psycopg2.extras import RealDictCursor

from .base_processor import BaseSyncProcessor


class FortnightSyncProcessor(BaseSyncProcessor):
    """Processor for syncing employee fortnights to Google Sheets."""

    @property
    def worksheet_name(self) -> str:
        return 'EmployeeFortnights'

    @property
    def table_name(self) -> str:
        return 'employee_fortnights'

    @property
    def last_column(self) -> str:
        return 'R'  # 18 columns

    def fetch_record(self, record_id: int) -> Optional[dict]:
        """Fetch employee fortnight from PostgreSQL."""
        with self.db_conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT
                    ef.id,
                    ef.employee_id,
                    e.name as employee_name,
                    ef.year,
                    ef.month,
                    ef.fortnight,
                    ef.total_shifts,
                    ef.total_worked_hours,
                    ef.total_sales,
                    ef.total_commissions,
                    ef.total_hourly_pay,
                    ef.total_made,
                    ef.bonus_counter_true_count,
                    ef.bonus_amount,
                    ef.total_salary,
                    ef.is_paid,
                    ef.payment_date,
                    ef.created_at
                FROM employee_fortnights ef
                LEFT JOIN employees e ON ef.employee_id = e.id
                WHERE ef.id = %s
            """, (record_id,))
            return cur.fetchone()

    def format_row(self, record: dict) -> List[Any]:
        """Format fortnight for Google Sheets.

        Columns: ID, EmployeeID, EmployeeName, Year, Month, Fortnight, TotalShifts,
                 TotalWorkedHours, TotalSales, TotalCommissions, TotalHourlyPay,
                 TotalMade, BonusCounterCount, BonusAmount, TotalSalary, IsPaid,
                 PaymentDate, CreatedAt
        """
        f = self._safe_float
        return [
            record['id'],
            record['employee_id'],
            self._safe_str(record['employee_name']),
            record['year'],
            record['month'],
            record['fortnight'],
            record['total_shifts'] if record['total_shifts'] else 0,
            f(record['total_worked_hours']),
            f(record['total_sales']),
            f(record['total_commissions']),
            f(record['total_hourly_pay']),
            f(record['total_made']),
            record['bonus_counter_true_count'] if record['bonus_counter_true_count'] else 0,
            f(record['bonus_amount']),
            f(record['total_salary']),
            self._bool_str(record['is_paid']),
            self._format_dt(record['payment_date'], '%Y-%m-%d'),
            self._format_dt(record['created_at']),
        ]
