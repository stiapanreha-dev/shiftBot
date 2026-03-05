"""Shift sync processor."""

from typing import List, Optional, Any

from psycopg2.extras import RealDictCursor

from .base_processor import BaseSyncProcessor


class ShiftSyncProcessor(BaseSyncProcessor):
    """Processor for syncing shifts to Google Sheets."""

    @property
    def worksheet_name(self) -> str:
        return 'Shifts'

    @property
    def table_name(self) -> str:
        return 'shifts'

    @property
    def last_column(self) -> str:
        return 'T'  # 20 columns (added Model E - Madison)

    def fetch_record(self, record_id: int) -> Optional[dict]:
        """Fetch shift with product data from PostgreSQL."""
        with self.db_conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT
                    s.id,
                    s.date,
                    s.employee_id,
                    s.employee_name,
                    s.clock_in,
                    s.clock_out,
                    s.worked_hours,
                    s.total_sales,
                    s.net_sales,
                    s.commission_pct,
                    s.total_hourly,
                    s.commissions,
                    s.total_made,
                    s.rolling_average,
                    s.bonus_counter,
                    COALESCE((SELECT amount FROM shift_products WHERE shift_id = s.id AND product_id = 1), 0) as model_a,
                    COALESCE((SELECT amount FROM shift_products WHERE shift_id = s.id AND product_id = 2), 0) as model_b,
                    COALESCE((SELECT amount FROM shift_products WHERE shift_id = s.id AND product_id = 3), 0) as model_c,
                    COALESCE((SELECT amount FROM shift_products WHERE shift_id = s.id AND product_id = 9), 0) as model_d,
                    COALESCE((SELECT amount FROM shift_products WHERE shift_id = s.id AND product_id = 11), 0) as model_e
                FROM shifts s
                WHERE s.id = %s
            """, (record_id,))
            return cur.fetchone()

    def format_row(self, record: dict) -> List[Any]:
        """Format shift for Google Sheets.

        Columns: ID, Date, EmployeeID, EmployeeName, ClockIn, ClockOut, WorkedHours,
                 TotalSales, NetSales, CommissionPct, TotalHourly, Commissions, TotalMade,
                 RollingAverage, BonusCounter, ModelA, ModelB, ModelC, ModelD, ModelE
        """
        f = self._safe_float
        dt = self._format_dt
        return [
            record['id'],
            dt(record['date']),
            record['employee_id'],
            record['employee_name'],
            dt(record['clock_in']),
            dt(record['clock_out']),
            f(record['worked_hours']),
            f(record['total_sales']),
            f(record['net_sales']),
            f(record['commission_pct']),
            f(record['total_hourly']),
            f(record['commissions']),
            f(record['total_made']),
            f(record['rolling_average']),
            self._bool_str(record['bonus_counter']),
            f(record['model_a']),
            f(record['model_b']),
            f(record['model_c']),
            f(record['model_d']),
            f(record['model_e']),
        ]
