"""Base class for sync processors."""

import logging
from abc import ABC, abstractmethod
from typing import List, Optional, Any

import gspread

logger = logging.getLogger(__name__)


class BaseSyncProcessor(ABC):
    """Base class for synchronizing PostgreSQL tables to Google Sheets.

    Each subclass handles synchronization for a specific table.
    """

    def __init__(self, spreadsheet: gspread.Spreadsheet, db_conn):
        """Initialize processor.

        Args:
            spreadsheet: Google Sheets spreadsheet object
            db_conn: PostgreSQL connection
        """
        self.spreadsheet = spreadsheet
        self.db_conn = db_conn

    @property
    @abstractmethod
    def worksheet_name(self) -> str:
        """Name of the target worksheet in Google Sheets."""
        pass

    @property
    @abstractmethod
    def table_name(self) -> str:
        """Name of the source PostgreSQL table."""
        pass

    @property
    def id_column(self) -> int:
        """Column index (1-based) containing the record ID. Default: 1"""
        return 1

    @property
    def last_column(self) -> str:
        """Last column letter for updates. Override in subclasses."""
        return 'Z'

    def process(self, record_id: int, operation: str, data: dict) -> bool:
        """Process a sync record.

        Args:
            record_id: Record ID
            operation: INSERT, UPDATE, or DELETE
            data: Record data from sync_queue

        Returns:
            True if successful
        """
        try:
            worksheet = self.spreadsheet.worksheet(self.worksheet_name)

            if operation == 'DELETE':
                return self._handle_delete(worksheet, record_id)
            else:
                return self._handle_upsert(worksheet, record_id)

        except Exception as e:
            logger.error(f"Failed to sync {self.table_name} {record_id}: {e}")
            import traceback
            logger.error(traceback.format_exc())
            raise

    def _handle_delete(self, worksheet: gspread.Worksheet, record_id: int) -> bool:
        """Handle DELETE operation.

        Args:
            worksheet: Target worksheet
            record_id: Record ID to delete

        Returns:
            True if successful
        """
        cell = self._find_row(worksheet, record_id)
        if cell:
            worksheet.delete_rows(cell.row)
            logger.info(f"Deleted {self.table_name} {record_id} from Google Sheets")
        return True

    def _handle_upsert(self, worksheet: gspread.Worksheet, record_id: int) -> bool:
        """Handle INSERT/UPDATE operation.

        Args:
            worksheet: Target worksheet
            record_id: Record ID

        Returns:
            True if successful
        """
        # Get record data from database
        record = self.fetch_record(record_id)
        if not record:
            logger.warning(f"{self.table_name} {record_id} not found in database")
            return False

        # Format row data
        row_data = self.format_row(record)

        # Find existing row or append
        cell = self._find_row(worksheet, record_id)
        if cell:
            range_str = f'A{cell.row}:{self.last_column}{cell.row}'
            worksheet.update(range_str, [row_data])
            logger.info(f"Updated {self.table_name} {record_id} in Google Sheets")
        else:
            worksheet.append_row(row_data)
            logger.info(f"Inserted {self.table_name} {record_id} to Google Sheets")

        return True

    def _find_row(self, worksheet: gspread.Worksheet, record_id: int) -> Optional[gspread.Cell]:
        """Find row by record ID.

        Args:
            worksheet: Target worksheet
            record_id: Record ID to find

        Returns:
            Cell object or None if not found
        """
        # gspread 6.x returns None if not found (no exception)
        return worksheet.find(str(record_id), in_column=self.id_column)

    @abstractmethod
    def fetch_record(self, record_id: int) -> Optional[dict]:
        """Fetch record data from PostgreSQL.

        Args:
            record_id: Record ID

        Returns:
            Record data or None if not found
        """
        pass

    @abstractmethod
    def format_row(self, record: dict) -> List[Any]:
        """Format record as row data for Google Sheets.

        Args:
            record: Record data from database

        Returns:
            List of cell values
        """
        pass
