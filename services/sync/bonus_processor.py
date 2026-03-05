"""Bonus sync processor."""

from typing import List, Optional, Any

from psycopg2.extras import RealDictCursor

from .base_processor import BaseSyncProcessor


class BonusSyncProcessor(BaseSyncProcessor):
    """Processor for syncing active bonuses to Google Sheets."""

    @property
    def worksheet_name(self) -> str:
        return 'ActiveBonuses'

    @property
    def table_name(self) -> str:
        return 'active_bonuses'

    @property
    def last_column(self) -> str:
        return 'G'  # 7 columns

    def fetch_record(self, record_id: int) -> Optional[dict]:
        """Fetch bonus from PostgreSQL."""
        with self.db_conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT id, employee_id, bonus_type, value, applied, shift_id, created_at
                FROM active_bonuses
                WHERE id = %s
            """, (record_id,))
            return cur.fetchone()

    def format_row(self, record: dict) -> List[Any]:
        """Format bonus for Google Sheets.

        Columns: ID, EmployeeID, BonusType, Value, Applied, ShiftID, CreatedAt
        """
        return [
            record['id'],
            record['employee_id'],
            record['bonus_type'],
            self._safe_float(record['value']),
            self._bool_str(record['applied']),
            self._safe_str(record['shift_id']),
            self._format_dt(record['created_at']),
        ]
