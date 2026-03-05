"""HUSH transaction sync processor."""

from typing import List, Optional, Any

from psycopg2.extras import RealDictCursor

from .base_processor import BaseSyncProcessor


class HushTransactionSyncProcessor(BaseSyncProcessor):
    """Processor for syncing HUSH transactions to Google Sheets."""

    @property
    def worksheet_name(self) -> str:
        return 'HushTransactions'

    @property
    def table_name(self) -> str:
        return 'hush_transactions'

    @property
    def last_column(self) -> str:
        return 'H'  # 8 columns

    def fetch_record(self, record_id: int) -> Optional[dict]:
        """Fetch HUSH transaction from PostgreSQL."""
        with self.db_conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT ht.id, ht.employee_id, ht.amount, ht.transaction_type,
                       ht.description, ht.rank_id, ht.balance_after, ht.created_at,
                       r.name as rank_name
                FROM hush_transactions ht
                LEFT JOIN ranks r ON r.id = ht.rank_id
                WHERE ht.id = %s
            """, (record_id,))
            return cur.fetchone()

    def format_row(self, record: dict) -> List[Any]:
        """Format HUSH transaction for Google Sheets.

        Columns: ID, EmployeeID, Amount, Type, Description, RankName, BalanceAfter, CreatedAt
        """
        return [
            record['id'],
            record['employee_id'],
            self._safe_float(record['amount']),
            self._safe_str(record['transaction_type']),
            self._safe_str(record['description']),
            self._safe_str(record['rank_name']),
            self._safe_float(record['balance_after']),
            self._format_dt(record['created_at']),
        ]
