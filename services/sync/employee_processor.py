"""Employee sync processor."""

from typing import List, Optional, Any

from psycopg2.extras import RealDictCursor

from .base_processor import BaseSyncProcessor


class EmployeeSyncProcessor(BaseSyncProcessor):
    """Processor for syncing employees to Google Sheets EmployeeSettings."""

    @property
    def worksheet_name(self) -> str:
        return 'EmployeeSettings'

    @property
    def table_name(self) -> str:
        return 'employees'

    @property
    def last_column(self) -> str:
        return 'E'  # 5 columns

    def fetch_record(self, record_id: int) -> Optional[dict]:
        """Fetch employee from PostgreSQL."""
        with self.db_conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT id, name, telegram_id, hourly_wage, sales_commission
                FROM employees
                WHERE id = %s
            """, (record_id,))
            return cur.fetchone()

    def format_row(self, record: dict) -> List[Any]:
        """Format employee for Google Sheets.

        Columns: TelegramID, Name, HourlyWage, SalesCommission, ID
        """
        return [
            record['telegram_id'] if record['telegram_id'] else record['id'],
            record['name'],
            float(record['hourly_wage']) if record['hourly_wage'] else 15.0,
            float(record['sales_commission']) if record['sales_commission'] else 6.0,
            record['id']
        ]
