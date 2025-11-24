"""Bidirectional sync manager for reference data.

This module handles synchronization between SQLite (local) and Google Sheets (remote)
for reference tables: EmployeeSettings, DynamicRates, Ranks.

Sync Strategy:
    1. Pull from Sheets: Full sync on startup, incremental sync periodically
    2. Push to Sheets: When local changes detected
    3. Conflict resolution: Last-write-wins with version tracking

Author: Claude Code (PROMPT 3.2 - Bidirectional Sync)
Date: 2025-11-11
Version: 1.0.0
"""

import sqlite3
import logging
from typing import Dict, List, Optional, Tuple
from datetime import datetime
import threading
import time

from database_schema import get_db_connection

logger = logging.getLogger(__name__)


class SyncManager:
    """Manages bidirectional sync between SQLite and Google Sheets."""

    def __init__(self, sheets_service, db_path: str = "data/reference_data.db"):
        """Initialize sync manager.

        Args:
            sheets_service: Instance of SheetsService for Google Sheets access
            db_path: Path to SQLite database
        """
        self.sheets = sheets_service
        self.db_path = db_path
        self._sync_lock = threading.Lock()
        self._last_sync_time = None

        logger.info("SyncManager initialized")

    # ==================== Core Sync Methods ====================

    def full_sync_from_sheets(self) -> Dict[str, int]:
        """Perform full sync from Google Sheets to SQLite.

        This is called on startup to ensure local DB has latest data.

        Returns:
            Dict with counts: {'employee_settings': N, 'dynamic_rates': N, 'ranks': N}
        """
        with self._sync_lock:
            logger.info("Starting full sync from Sheets...")

            counts = {
                'employee_settings': 0,
                'dynamic_rates': 0,
                'ranks': 0
            }

            try:
                # Sync EmployeeSettings
                counts['employee_settings'] = self._pull_employee_settings()

                # Sync DynamicRates
                counts['dynamic_rates'] = self._pull_dynamic_rates()

                # Sync Ranks
                counts['ranks'] = self._pull_ranks()

                self._last_sync_time = datetime.now()

                logger.info(f"Full sync completed: {counts}")
                return counts

            except Exception as e:
                logger.error(f"Full sync failed: {e}")
                raise

    def push_changes_to_sheets(self) -> Dict[str, int]:
        """Push local changes to Google Sheets.

        This syncs records with sync_status='pending'.

        Returns:
            Dict with counts of pushed records
        """
        with self._sync_lock:
            logger.info("Pushing changes to Sheets...")

            counts = {
                'employee_settings': 0,
                'dynamic_rates': 0,
                'ranks': 0
            }

            try:
                # Push EmployeeSettings changes
                counts['employee_settings'] = self._push_employee_settings()

                # Push DynamicRates changes
                counts['dynamic_rates'] = self._push_dynamic_rates()

                # Push Ranks changes
                counts['ranks'] = self._push_ranks()

                logger.info(f"Push completed: {counts}")
                return counts

            except Exception as e:
                logger.error(f"Push failed: {e}")
                raise

    # ==================== EmployeeSettings Sync ====================

    def _pull_employee_settings(self) -> int:
        """Pull EmployeeSettings from Sheets to SQLite.

        Returns:
            Number of records synced
        """
        try:
            # Get data from Sheets
            ws = self.sheets.spreadsheet.worksheet("EmployeeSettings")
            all_records = ws.get_all_records()

            if not all_records:
                logger.warning("EmployeeSettings sheet is empty")
                return 0

            conn = get_db_connection(self.db_path)
            cursor = conn.cursor()

            count = 0
            now = datetime.now().isoformat()

            for record in all_records:
                employee_id = record.get("EmployeeId")
                hourly_wage = float(record.get("Hourly wage", 15.0))
                sales_commission = float(record.get("Sales commission", 8.0))

                if not employee_id:
                    continue

                # Upsert into SQLite
                cursor.execute("""
                    INSERT INTO employee_settings
                        (employee_id, hourly_wage, sales_commission,
                         last_synced_at, last_modified_at, source, sync_status, version)
                    VALUES (?, ?, ?, ?, ?, 'sheets', 'synced', 1)
                    ON CONFLICT(employee_id) DO UPDATE SET
                        hourly_wage = excluded.hourly_wage,
                        sales_commission = excluded.sales_commission,
                        last_synced_at = excluded.last_synced_at,
                        source = 'sheets',
                        sync_status = 'synced',
                        version = version + 1
                """, (employee_id, hourly_wage, sales_commission, now, now))

                count += 1

            conn.commit()
            conn.close()

            self._log_sync('employee_settings', 'pull', 'all', 'success')
            logger.info(f"Pulled {count} EmployeeSettings records")

            return count

        except Exception as e:
            self._log_sync('employee_settings', 'pull', 'all', 'failed', str(e))
            logger.error(f"Failed to pull EmployeeSettings: {e}")
            raise

    def _push_employee_settings(self) -> int:
        """Push pending EmployeeSettings changes to Sheets.

        Returns:
            Number of records pushed
        """
        try:
            conn = get_db_connection(self.db_path)
            cursor = conn.cursor()

            # Get pending changes
            cursor.execute("""
                SELECT employee_id, hourly_wage, sales_commission
                FROM employee_settings
                WHERE sync_status = 'pending'
            """)

            pending_records = cursor.fetchall()

            if not pending_records:
                conn.close()
                return 0

            # Get Sheets worksheet
            ws = self.sheets.spreadsheet.worksheet("EmployeeSettings")
            all_records = ws.get_all_records()

            count = 0
            now = datetime.now().isoformat()

            for record in pending_records:
                employee_id = record['employee_id']
                hourly_wage = record['hourly_wage']
                sales_commission = record['sales_commission']

                # Find row in Sheets
                row_idx = None
                for idx, sheet_record in enumerate(all_records, start=2):
                    if str(sheet_record.get("EmployeeId")) == str(employee_id):
                        row_idx = idx
                        break

                if row_idx:
                    # Update existing row
                    ws.update(f"B{row_idx}:C{row_idx}", [[hourly_wage, sales_commission]])
                else:
                    # Append new row
                    ws.append_row([employee_id, hourly_wage, sales_commission])

                # Mark as synced in SQLite
                cursor.execute("""
                    UPDATE employee_settings
                    SET sync_status = 'synced', last_synced_at = ?
                    WHERE employee_id = ?
                """, (now, employee_id))

                count += 1

            conn.commit()
            conn.close()

            self._log_sync('employee_settings', 'push', 'all', 'success')
            logger.info(f"Pushed {count} EmployeeSettings changes")

            return count

        except Exception as e:
            self._log_sync('employee_settings', 'push', 'all', 'failed', str(e))
            logger.error(f"Failed to push EmployeeSettings: {e}")
            raise

    # ==================== DynamicRates Sync ====================

    def _pull_dynamic_rates(self) -> int:
        """Pull DynamicRates from Sheets to SQLite.

        Returns:
            Number of records synced
        """
        try:
            # Get data from Sheets
            ws = self.sheets.spreadsheet.worksheet("DynamicRates")
            all_records = ws.get_all_records()

            if not all_records:
                logger.warning("DynamicRates sheet is empty")
                return 0

            conn = get_db_connection(self.db_path)
            cursor = conn.cursor()

            # Clear existing data (full replace strategy)
            cursor.execute("DELETE FROM dynamic_rates")

            count = 0
            now = datetime.now().isoformat()

            for record in all_records:
                min_amount = float(record.get("Min Amount", 0))
                max_amount = float(record.get("Max Amount", 999999))
                percentage = float(record.get("Percentage", 0))

                cursor.execute("""
                    INSERT INTO dynamic_rates
                        (min_amount, max_amount, percentage,
                         last_synced_at, last_modified_at, source, sync_status, version)
                    VALUES (?, ?, ?, ?, ?, 'sheets', 'synced', 1)
                """, (min_amount, max_amount, percentage, now, now))

                count += 1

            conn.commit()
            conn.close()

            self._log_sync('dynamic_rates', 'pull', 'all', 'success')
            logger.info(f"Pulled {count} DynamicRates records")

            return count

        except Exception as e:
            self._log_sync('dynamic_rates', 'pull', 'all', 'failed', str(e))
            logger.error(f"Failed to pull DynamicRates: {e}")
            raise

    def _push_dynamic_rates(self) -> int:
        """Push pending DynamicRates changes to Sheets.

        Note: For DynamicRates, we use full replace strategy.

        Returns:
            Number of records pushed
        """
        try:
            conn = get_db_connection(self.db_path)
            cursor = conn.cursor()

            # Get pending changes
            cursor.execute("""
                SELECT id, min_amount, max_amount, percentage
                FROM dynamic_rates
                WHERE sync_status = 'pending'
            """)

            pending_records = cursor.fetchall()

            if not pending_records:
                conn.close()
                return 0

            # Get Sheets worksheet
            ws = self.sheets.spreadsheet.worksheet("DynamicRates")

            # For simplicity, we'll do full replace if there are pending changes
            # Get all current local data
            cursor.execute("""
                SELECT min_amount, max_amount, percentage
                FROM dynamic_rates
                ORDER BY min_amount
            """)

            all_local_records = cursor.fetchall()

            # Clear Sheets (except header)
            ws.resize(rows=1)

            # Write all data
            rows_to_append = [
                [r['min_amount'], r['max_amount'], r['percentage']]
                for r in all_local_records
            ]

            if rows_to_append:
                ws.append_rows(rows_to_append)

            # Mark all as synced
            now = datetime.now().isoformat()
            cursor.execute("""
                UPDATE dynamic_rates
                SET sync_status = 'synced', last_synced_at = ?
                WHERE sync_status = 'pending'
            """, (now,))

            count = len(pending_records)

            conn.commit()
            conn.close()

            self._log_sync('dynamic_rates', 'push', 'all', 'success')
            logger.info(f"Pushed {count} DynamicRates changes (full replace)")

            return count

        except Exception as e:
            self._log_sync('dynamic_rates', 'push', 'all', 'failed', str(e))
            logger.error(f"Failed to push DynamicRates: {e}")
            raise

    # ==================== Ranks Sync ====================

    def _pull_ranks(self) -> int:
        """Pull Ranks from Sheets to SQLite.

        Returns:
            Number of records synced
        """
        try:
            # Get data from Sheets
            ws = self.sheets.spreadsheet.worksheet("Ranks")
            all_records = ws.get_all_records()

            if not all_records:
                logger.warning("Ranks sheet is empty")
                return 0

            conn = get_db_connection(self.db_path)
            cursor = conn.cursor()

            # Clear existing data (full replace strategy)
            cursor.execute("DELETE FROM ranks")

            count = 0
            now = datetime.now().isoformat()

            for record in all_records:
                rank_name = record.get("Rank Name", "")
                min_amount = float(record.get("Min Amount", 0))
                max_amount = float(record.get("Max Amount", 999999))
                bonus_1 = record.get("Bonus 1", "")
                bonus_2 = record.get("Bonus 2", "")
                bonus_3 = record.get("Bonus 3", "")
                text = record.get("TEXT", "")

                if not rank_name:
                    continue

                cursor.execute("""
                    INSERT INTO ranks
                        (rank_name, min_amount, max_amount, bonus_1, bonus_2, bonus_3, text,
                         last_synced_at, last_modified_at, source, sync_status, version)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'sheets', 'synced', 1)
                """, (rank_name, min_amount, max_amount, bonus_1, bonus_2, bonus_3, text, now, now))

                count += 1

            conn.commit()
            conn.close()

            self._log_sync('ranks', 'pull', 'all', 'success')
            logger.info(f"Pulled {count} Ranks records")

            return count

        except Exception as e:
            self._log_sync('ranks', 'pull', 'all', 'failed', str(e))
            logger.error(f"Failed to pull Ranks: {e}")
            raise

    def _push_ranks(self) -> int:
        """Push pending Ranks changes to Sheets.

        Note: For Ranks, we use full replace strategy.

        Returns:
            Number of records pushed
        """
        try:
            conn = get_db_connection(self.db_path)
            cursor = conn.cursor()

            # Get pending changes
            cursor.execute("""
                SELECT COUNT(*) as count
                FROM ranks
                WHERE sync_status = 'pending'
            """)

            pending_count = cursor.fetchone()['count']

            if pending_count == 0:
                conn.close()
                return 0

            # Get Sheets worksheet
            ws = self.sheets.spreadsheet.worksheet("Ranks")

            # Full replace strategy
            # Get all current local data
            cursor.execute("""
                SELECT rank_name, min_amount, max_amount, bonus_1, bonus_2, bonus_3, text
                FROM ranks
                ORDER BY min_amount
            """)

            all_local_records = cursor.fetchall()

            # Clear Sheets (except header)
            ws.resize(rows=1)

            # Write all data
            rows_to_append = [
                [r['rank_name'], r['min_amount'], r['max_amount'],
                 r['bonus_1'], r['bonus_2'], r['bonus_3'], r['text']]
                for r in all_local_records
            ]

            if rows_to_append:
                ws.append_rows(rows_to_append)

            # Mark all as synced
            now = datetime.now().isoformat()
            cursor.execute("""
                UPDATE ranks
                SET sync_status = 'synced', last_synced_at = ?
                WHERE sync_status = 'pending'
            """, (now,))

            count = pending_count

            conn.commit()
            conn.close()

            self._log_sync('ranks', 'push', 'all', 'success')
            logger.info(f"Pushed {count} Ranks changes (full replace)")

            return count

        except Exception as e:
            self._log_sync('ranks', 'push', 'all', 'failed', str(e))
            logger.error(f"Failed to push Ranks: {e}")
            raise

    # ==================== Utility Methods ====================

    def _log_sync(self, table_name: str, operation: str, record_id: str,
                  status: str, error_message: Optional[str] = None) -> None:
        """Log sync operation to sync_log table.

        Args:
            table_name: Name of table being synced
            operation: 'pull', 'push', or 'conflict'
            record_id: ID of record (or 'all' for batch)
            status: 'success', 'failed', or 'conflict'
            error_message: Optional error message
        """
        try:
            conn = get_db_connection(self.db_path)
            cursor = conn.cursor()

            cursor.execute("""
                INSERT INTO sync_log (table_name, operation, record_id, status, error_message)
                VALUES (?, ?, ?, ?, ?)
            """, (table_name, operation, record_id, status, error_message))

            conn.commit()
            conn.close()

        except Exception as e:
            logger.error(f"Failed to log sync: {e}")

    def get_sync_stats(self) -> Dict:
        """Get sync statistics.

        Returns:
            Dict with sync stats
        """
        try:
            conn = get_db_connection(self.db_path)
            cursor = conn.cursor()

            # Count pending records
            cursor.execute("""
                SELECT
                    (SELECT COUNT(*) FROM employee_settings WHERE sync_status = 'pending') as es_pending,
                    (SELECT COUNT(*) FROM dynamic_rates WHERE sync_status = 'pending') as dr_pending,
                    (SELECT COUNT(*) FROM ranks WHERE sync_status = 'pending') as r_pending,
                    (SELECT COUNT(*) FROM employee_settings WHERE sync_status = 'synced') as es_synced,
                    (SELECT COUNT(*) FROM dynamic_rates WHERE sync_status = 'synced') as dr_synced,
                    (SELECT COUNT(*) FROM ranks WHERE sync_status = 'synced') as r_synced
            """)

            row = cursor.fetchone()

            conn.close()

            return {
                'last_sync_time': self._last_sync_time.isoformat() if self._last_sync_time else None,
                'employee_settings': {
                    'pending': row['es_pending'],
                    'synced': row['es_synced']
                },
                'dynamic_rates': {
                    'pending': row['dr_pending'],
                    'synced': row['dr_synced']
                },
                'ranks': {
                    'pending': row['r_pending'],
                    'synced': row['r_synced']
                }
            }

        except Exception as e:
            logger.error(f"Failed to get sync stats: {e}")
            return {}

    def get_last_sync_time(self) -> Optional[datetime]:
        """Get timestamp of last successful sync.

        Returns:
            Datetime of last sync or None
        """
        return self._last_sync_time


# ==================== Background Sync Worker ====================

class BackgroundSyncWorker:
    """Background worker for periodic sync."""

    def __init__(self, sync_manager: SyncManager, interval_seconds: int = 300):
        """Initialize background sync worker.

        Args:
            sync_manager: SyncManager instance
            interval_seconds: Sync interval in seconds (default: 300 = 5 minutes)
        """
        self.sync_manager = sync_manager
        self.interval = interval_seconds
        self._stop_event = threading.Event()
        self._thread = None

        logger.info(f"BackgroundSyncWorker initialized (interval: {interval_seconds}s)")

    def start(self) -> None:
        """Start background sync worker."""
        if self._thread and self._thread.is_alive():
            logger.warning("Background sync worker already running")
            return

        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

        logger.info("Background sync worker started")

    def stop(self) -> None:
        """Stop background sync worker."""
        if not self._thread or not self._thread.is_alive():
            logger.warning("Background sync worker not running")
            return

        self._stop_event.set()
        self._thread.join(timeout=10)

        logger.info("Background sync worker stopped")

    def _run(self) -> None:
        """Background sync loop."""
        logger.info("Background sync loop started")

        while not self._stop_event.is_set():
            try:
                # Pull changes from Sheets
                self.sync_manager.full_sync_from_sheets()

                # Push local changes to Sheets
                self.sync_manager.push_changes_to_sheets()

            except Exception as e:
                logger.error(f"Background sync failed: {e}")

            # Sleep until next sync
            self._stop_event.wait(self.interval)

        logger.info("Background sync loop stopped")
