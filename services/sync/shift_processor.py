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
        return 'S'  # 19 columns (added Model D)

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
                    COALESCE((SELECT amount FROM shift_products WHERE shift_id = s.id AND product_id = 9), 0) as model_d
                FROM shifts s
                WHERE s.id = %s
            """, (record_id,))
            return cur.fetchone()

    def format_row(self, record: dict) -> List[Any]:
        """Format shift for Google Sheets.

        Columns: ID, Date, EmployeeID, EmployeeName, ClockIn, ClockOut, WorkedHours,
                 ModelA, ModelB, ModelC, ModelD, TotalSales, NetSales, CommissionPct,
                 TotalHourly, Commissions, TotalMade, RollingAverage, BonusCounter
        """
        return [
            record['id'],
            record['date'].strftime('%Y-%m-%d %H:%M:%S') if record['date'] else '',
            record['employee_id'],
            record['employee_name'],
            record['clock_in'].strftime('%Y-%m-%d %H:%M:%S') if record['clock_in'] else '',
            record['clock_out'].strftime('%Y-%m-%d %H:%M:%S') if record['clock_out'] else '',
            float(record['worked_hours']) if record['worked_hours'] else 0,
            float(record['model_a']) if record['model_a'] else 0,
            float(record['model_b']) if record['model_b'] else 0,
            float(record['model_c']) if record['model_c'] else 0,
            float(record['model_d']) if record['model_d'] else 0,
            float(record['total_sales']) if record['total_sales'] else 0,
            float(record['net_sales']) if record['net_sales'] else 0,
            float(record['commission_pct']) if record['commission_pct'] else 0,
            float(record['total_hourly']) if record['total_hourly'] else 0,
            float(record['commissions']) if record['commissions'] else 0,
            float(record['total_made']) if record['total_made'] else 0,
            float(record['rolling_average']) if record['rolling_average'] else 0,
            'TRUE' if record['bonus_counter'] else 'FALSE'
        ]
