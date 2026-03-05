"""Employee rank sync processor."""

import logging
from typing import List, Optional, Any

import gspread
from psycopg2.extras import RealDictCursor

from .base_processor import BaseSyncProcessor

logger = logging.getLogger(__name__)


class RankSyncProcessor(BaseSyncProcessor):
    """Processor for syncing employee ranks to Google Sheets.

    Note: This processor uses composite key (employee_id, year, month)
    instead of simple ID for finding rows.
    """

    @property
    def worksheet_name(self) -> str:
        return 'EmployeeRanks'

    @property
    def table_name(self) -> str:
        return 'employee_ranks'

    @property
    def last_column(self) -> str:
        return 'G'  # 7 columns

    def fetch_record(self, record_id: int) -> Optional[dict]:
        """Fetch employee rank from PostgreSQL."""
        with self.db_conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT
                    er.id,
                    er.employee_id,
                    er.year,
                    er.month,
                    r_current.name as current_rank,
                    r_prev.name as previous_rank,
                    er.updated_at,
                    er.notified
                FROM employee_ranks er
                LEFT JOIN ranks r_current ON er.current_rank_id = r_current.id
                LEFT JOIN ranks r_prev ON er.previous_rank_id = r_prev.id
                WHERE er.id = %s
            """, (record_id,))
            return cur.fetchone()

    def format_row(self, record: dict) -> List[Any]:
        """Format employee rank for Google Sheets.

        Columns: EmployeeID, Year, Month, CurrentRank, PreviousRank, UpdatedAt, Notified
        """
        return [
            record['employee_id'],
            record['year'],
            record['month'],
            self._safe_str(record['current_rank']),
            self._safe_str(record['previous_rank']),
            self._format_dt(record['updated_at']),
            self._bool_str(record['notified']),
        ]

    def _handle_upsert(self, worksheet: gspread.Worksheet, record_id: int) -> bool:
        """Handle INSERT/UPDATE using composite key lookup.

        Override to use (employee_id, year, month) as composite key.
        """
        record = self.fetch_record(record_id)
        if not record:
            logger.warning(f"{self.table_name} {record_id} not found in database")
            return False

        row_data = self.format_row(record)

        # Find by composite key (employee_id, year, month)
        all_values = worksheet.get_all_values()
        found_row = None

        for idx, row in enumerate(all_values[1:], start=2):  # Skip header
            if (len(row) >= 3 and
                str(row[0]) == str(record['employee_id']) and
                str(row[1]) == str(record['year']) and
                str(row[2]) == str(record['month'])):
                found_row = idx
                break

        if found_row:
            worksheet.update(f'A{found_row}:{self.last_column}{found_row}', [row_data])
            logger.info(f"Updated {self.table_name} {record_id} in Google Sheets")
        else:
            worksheet.append_row(row_data)
            logger.info(f"Inserted {self.table_name} {record_id} to Google Sheets")

            # Deduplication check: verify no duplicate was created by concurrent write
            all_values_after = worksheet.get_all_values()
            dup_rows = []
            for idx, row in enumerate(all_values_after[1:], start=2):
                if (len(row) >= 3 and
                    str(row[0]) == str(record['employee_id']) and
                    str(row[1]) == str(record['year']) and
                    str(row[2]) == str(record['month'])):
                    dup_rows.append(idx)

            if len(dup_rows) > 1:
                # Keep the last row, delete earlier duplicates
                for dup_row in sorted(dup_rows[:-1], reverse=True):
                    worksheet.delete_rows(dup_row)
                logger.warning(f"Removed {len(dup_rows) - 1} duplicate row(s) for {self.table_name} {record_id}")

        return True
