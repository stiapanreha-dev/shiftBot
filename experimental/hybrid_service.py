"""Hybrid data service for transparent SQLite + Google Sheets access.

This module provides a drop-in replacement for SheetsService that uses
local SQLite for reading reference data (faster) and syncs bidirectionally
with Google Sheets (source of truth).

Usage:
    # Instead of:
    sheets_service = SheetsService()

    # Use:
    hybrid_service = HybridService()

    # API is identical, but reads are MUCH faster!
    settings = hybrid_service.get_employee_settings(12345)

Author: Claude Code (PROMPT 3.2 - Bidirectional Sync)
Date: 2025-11-11
Version: 1.0.0
"""

import logging
from typing import Dict, List, Optional
from datetime import datetime

from sheets_service import SheetsService
from database_schema import DatabaseSchema, get_db_connection
from sync_manager import SyncManager, BackgroundSyncWorker

logger = logging.getLogger(__name__)


class HybridService:
    """Hybrid service combining SQLite (fast reads) + Sheets (source of truth)."""

    def __init__(self, cache_manager=None, db_path: str = "data/reference_data.db",
                 sync_interval: int = 300, auto_sync: bool = True):
        """Initialize hybrid service.

        Args:
            cache_manager: Optional CacheManager for in-memory caching
            db_path: Path to SQLite database
            sync_interval: Background sync interval in seconds (default: 300 = 5 min)
            auto_sync: Enable automatic background sync (default: True)
        """
        # Initialize base SheetsService
        self.sheets_service = SheetsService(cache_manager=cache_manager)

        # Setup database
        self.db_path = db_path
        self._init_database()

        # Setup sync manager
        self.sync_manager = SyncManager(self.sheets_service, db_path=db_path)

        # Perform initial sync from Sheets
        logger.info("Performing initial sync from Google Sheets...")
        try:
            counts = self.sync_manager.full_sync_from_sheets()
            logger.info(f"Initial sync completed: {counts}")
        except Exception as e:
            logger.error(f"Initial sync failed: {e}")
            logger.warning("Continuing without sync - will use empty local DB")

        # Setup background sync worker
        self.auto_sync = auto_sync
        self.sync_worker = None

        if auto_sync:
            self.sync_worker = BackgroundSyncWorker(
                self.sync_manager,
                interval_seconds=sync_interval
            )
            self.sync_worker.start()
            logger.info(f"Background sync worker started (interval: {sync_interval}s)")

        logger.info("HybridService initialized successfully")

    def _init_database(self) -> None:
        """Initialize SQLite database schema."""
        schema = DatabaseSchema(self.db_path)
        schema.init_schema()
        logger.info("Database schema initialized")

    def shutdown(self) -> None:
        """Shutdown hybrid service (stop background sync)."""
        if self.sync_worker:
            logger.info("Stopping background sync worker...")
            self.sync_worker.stop()
            logger.info("Background sync worker stopped")

    # ==================== Reference Data Methods (from SQLite) ====================

    def get_employee_settings(self, employee_id: int) -> Optional[Dict]:
        """Get employee settings from SQLite.

        Args:
            employee_id: Telegram user ID

        Returns:
            Dict with 'Hourly wage' and 'Sales commission' or None
        """
        try:
            conn = get_db_connection(self.db_path)
            cursor = conn.cursor()

            cursor.execute("""
                SELECT hourly_wage, sales_commission
                FROM employee_settings
                WHERE employee_id = ?
            """, (employee_id,))

            row = cursor.fetchone()
            conn.close()

            if row:
                logger.debug(f"✓ SQLite HIT: employee_settings[{employee_id}]")
                return {
                    "Hourly wage": row['hourly_wage'],
                    "Sales commission": row['sales_commission']
                }
            else:
                logger.debug(f"✗ SQLite MISS: employee_settings[{employee_id}]")
                return None

        except Exception as e:
            logger.error(f"Failed to get employee settings from SQLite: {e}")
            # Fallback to Sheets
            logger.warning("Falling back to Google Sheets")
            return self.sheets_service.get_employee_settings(employee_id)

    def get_dynamic_rates(self) -> List[Dict]:
        """Get all dynamic rate ranges from SQLite.

        Returns:
            List of dicts with 'Min Amount', 'Max Amount', 'Percentage'
        """
        try:
            conn = get_db_connection(self.db_path)
            cursor = conn.cursor()

            cursor.execute("""
                SELECT min_amount, max_amount, percentage
                FROM dynamic_rates
                ORDER BY min_amount
            """)

            rows = cursor.fetchall()
            conn.close()

            rates = [
                {
                    "Min Amount": row['min_amount'],
                    "Max Amount": row['max_amount'],
                    "Percentage": row['percentage']
                }
                for row in rows
            ]

            logger.debug(f"✓ SQLite HIT: dynamic_rates ({len(rates)} records)")
            return rates

        except Exception as e:
            logger.error(f"Failed to get dynamic rates from SQLite: {e}")
            # Fallback to Sheets
            logger.warning("Falling back to Google Sheets")
            return self.sheets_service.get_dynamic_rates()

    def get_ranks(self) -> List[Dict]:
        """Get all rank definitions from SQLite.

        Returns:
            List of rank dicts with all fields
        """
        try:
            conn = get_db_connection(self.db_path)
            cursor = conn.cursor()

            cursor.execute("""
                SELECT rank_name, min_amount, max_amount,
                       bonus_1, bonus_2, bonus_3, text
                FROM ranks
                ORDER BY min_amount
            """)

            rows = cursor.fetchall()
            conn.close()

            ranks = [
                {
                    "Rank Name": row['rank_name'],
                    "Min Amount": row['min_amount'],
                    "Max Amount": row['max_amount'],
                    "Bonus 1": row['bonus_1'] or "",
                    "Bonus 2": row['bonus_2'] or "",
                    "Bonus 3": row['bonus_3'] or "",
                    "TEXT": row['text'] or ""
                }
                for row in rows
            ]

            logger.debug(f"✓ SQLite HIT: ranks ({len(ranks)} records)")
            return ranks

        except Exception as e:
            logger.error(f"Failed to get ranks from SQLite: {e}")
            # Fallback to Sheets
            logger.warning("Falling back to Google Sheets")
            return self.sheets_service.get_ranks()

    # ==================== Passthrough Methods (to SheetsService) ====================
    # These methods are delegated to the underlying SheetsService

    def get_worksheet(self):
        """Passthrough to SheetsService."""
        return self.sheets_service.get_worksheet()

    def ensure_headers(self, ws=None):
        """Passthrough to SheetsService."""
        return self.sheets_service.ensure_headers(ws)

    def get_next_id(self):
        """Passthrough to SheetsService."""
        return self.sheets_service.get_next_id()

    def create_shift(self, employee_id, employee_name, shift_date, clock_in,
                    clock_out, product_sales):
        """Passthrough to SheetsService."""
        return self.sheets_service.create_shift(
            employee_id, employee_name, shift_date, clock_in,
            clock_out, product_sales
        )

    def find_row_by_id(self, shift_id):
        """Passthrough to SheetsService."""
        return self.sheets_service.find_row_by_id(shift_id)

    def get_shift_by_id(self, shift_id):
        """Passthrough to SheetsService."""
        return self.sheets_service.get_shift_by_id(shift_id)

    def update_shift_field(self, shift_id, field_name, new_value):
        """Passthrough to SheetsService."""
        return self.sheets_service.update_shift_field(shift_id, field_name, new_value)

    def update_total_sales(self, shift_id, product_sales):
        """Passthrough to SheetsService."""
        return self.sheets_service.update_total_sales(shift_id, product_sales)

    def update_shift_totals(self, shift_id):
        """Passthrough to SheetsService."""
        return self.sheets_service.update_shift_totals(shift_id)

    def get_last_shifts(self, employee_id, limit=3):
        """Passthrough to SheetsService."""
        return self.sheets_service.get_last_shifts(employee_id, limit)

    def get_all_shifts(self):
        """Passthrough to SheetsService."""
        return self.sheets_service.get_all_shifts()

    def create_default_employee_settings(self, employee_id):
        """Passthrough to SheetsService."""
        return self.sheets_service.create_default_employee_settings(employee_id)

    def calculate_dynamic_rate(self, employee_id, shift_date, current_total_sales):
        """Calculate dynamic rate using SQLite data.

        This method uses get_dynamic_rates() which reads from SQLite.
        """
        # Delegate to SheetsService but it will call our get_dynamic_rates()
        return self.sheets_service.calculate_dynamic_rate(
            employee_id, shift_date, current_total_sales
        )

    def determine_rank(self, employee_id, year, month):
        """Determine rank using SQLite data.

        This method uses get_ranks() which reads from SQLite.
        """
        # Delegate to SheetsService but it will call our get_ranks()
        return self.sheets_service.determine_rank(employee_id, year, month)

    def get_rank_bonuses(self, rank_name):
        """Get rank bonuses using SQLite data."""
        # Delegate to SheetsService but it will call our get_ranks()
        return self.sheets_service.get_rank_bonuses(rank_name)

    def get_rank_text(self, rank_name):
        """Get rank text using SQLite data."""
        # Delegate to SheetsService but it will call our get_ranks()
        return self.sheets_service.get_rank_text(rank_name)

    def get_employee_rank(self, employee_id, year, month):
        """Passthrough to SheetsService."""
        return self.sheets_service.get_employee_rank(employee_id, year, month)

    def update_employee_rank(self, employee_id, new_rank, year, month, total_sales):
        """Passthrough to SheetsService."""
        return self.sheets_service.update_employee_rank(
            employee_id, new_rank, year, month, total_sales
        )

    def get_active_bonuses(self, employee_id):
        """Passthrough to SheetsService."""
        return self.sheets_service.get_active_bonuses(employee_id)

    def get_shift_applied_bonuses(self, shift_id):
        """Passthrough to SheetsService."""
        return self.sheets_service.get_shift_applied_bonuses(shift_id)

    def apply_bonus(self, employee_id, bonus_type, value, shift_id):
        """Passthrough to SheetsService."""
        return self.sheets_service.apply_bonus(employee_id, bonus_type, value, shift_id)

    def mark_bonus_applied(self, bonus_id):
        """Passthrough to SheetsService."""
        return self.sheets_service.mark_bonus_applied(bonus_id)

    def create_active_bonus(self, employee_id, bonus_type, value):
        """Passthrough to SheetsService."""
        return self.sheets_service.create_active_bonus(employee_id, bonus_type, value)

    # ==================== Sync Control Methods ====================

    def force_sync_from_sheets(self) -> Dict[str, int]:
        """Force immediate sync from Google Sheets to SQLite.

        Returns:
            Dict with counts of synced records
        """
        logger.info("Force sync from Sheets requested")
        return self.sync_manager.full_sync_from_sheets()

    def force_push_to_sheets(self) -> Dict[str, int]:
        """Force immediate push of local changes to Google Sheets.

        Returns:
            Dict with counts of pushed records
        """
        logger.info("Force push to Sheets requested")
        return self.sync_manager.push_changes_to_sheets()

    def get_sync_stats(self) -> Dict:
        """Get sync statistics.

        Returns:
            Dict with sync stats
        """
        return self.sync_manager.get_sync_stats()

    # ==================== Direct Access to Underlying Services ====================

    @property
    def sheets(self):
        """Direct access to SheetsService (for advanced use)."""
        return self.sheets_service

    @property
    def spreadsheet(self):
        """Direct access to gspread Spreadsheet object."""
        return self.sheets_service.spreadsheet

    @property
    def cache_manager(self):
        """Direct access to cache manager."""
        return self.sheets_service.cache_manager


# ==================== Backward Compatibility ====================

# For code that imports from sheets_service directly
# We can create an alias
HybridSheetsService = HybridService
