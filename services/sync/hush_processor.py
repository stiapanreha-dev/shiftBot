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
        created_at = record['created_at']
        if created_at:
            created_at = created_at.strftime('%Y-%m-%d %H:%M:%S')

        return [
            record['id'],
            record['employee_id'],
            float(record['amount']) if record['amount'] else 0,
            record['transaction_type'] or '',
            record['description'] or '',
            record['rank_name'] or '',
            float(record['balance_after']) if record['balance_after'] else 0,
            created_at or ''
        ]
