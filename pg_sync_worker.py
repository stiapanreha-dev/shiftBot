#!/usr/bin/env python3
"""PostgreSQL-to-Google Sheets sync worker.

This script processes the sync_queue table and synchronizes changes from
PostgreSQL to Google Sheets.

It runs as a separate systemd service and handles periodic synchronization.

Usage:
    python3 pg_sync_worker.py [--interval SECONDS] [--once]

Author: Claude Code (PostgreSQL sync worker)
Date: 2025-11-24
Version: 1.0.0
"""

import logging
import signal
import sys
import time
import argparse
import os
from datetime import datetime
from pathlib import Path
from collections import deque
from functools import wraps
import psycopg2
from psycopg2.extras import RealDictCursor
import gspread
from gspread.exceptions import APIError
from google.oauth2.service_account import Credentials

# Setup logging
log_dir = Path('/opt/alex12060-bot/logs')
log_dir.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_dir / 'sync_worker.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


class RateLimiter:
    """Simple rate limiter for Google Sheets API.

    Google Sheets API limits: 60 read requests per minute per user.
    We use 40 requests per minute to be safe.
    """

    def __init__(self, max_requests: int = 40, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.requests = deque()

    def wait_if_needed(self):
        """Wait if we've exceeded the rate limit."""
        now = time.time()

        # Remove old requests outside the window
        while self.requests and self.requests[0] < now - self.window_seconds:
            self.requests.popleft()

        # If at limit, wait until oldest request expires
        if len(self.requests) >= self.max_requests:
            wait_time = self.requests[0] + self.window_seconds - now + 0.5
            if wait_time > 0:
                logger.info(f"Rate limit reached, waiting {wait_time:.1f}s...")
                time.sleep(wait_time)
                # Clean up again after waiting
                now = time.time()
                while self.requests and self.requests[0] < now - self.window_seconds:
                    self.requests.popleft()

        # Record this request
        self.requests.append(time.time())


def retry_on_quota_error(max_retries: int = 3, base_delay: float = 30.0):
    """Decorator to retry on Google API quota errors (429)."""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_error = None
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except APIError as e:
                    if e.response.status_code == 429:
                        last_error = e
                        if attempt < max_retries:
                            delay = base_delay * (2 ** attempt)  # Exponential backoff
                            logger.warning(f"Quota exceeded (attempt {attempt + 1}/{max_retries + 1}), waiting {delay}s...")
                            time.sleep(delay)
                        else:
                            logger.error(f"Quota exceeded after {max_retries + 1} attempts")
                            raise
                    else:
                        raise
            raise last_error
        return wrapper
    return decorator


class PostgresSyncWorker:
    """Sync worker for PostgreSQL to Google Sheets synchronization."""

    def __init__(self, interval_seconds: int = 300):
        """Initialize sync worker.

        Args:
            interval_seconds: Sync interval in seconds (default: 300 = 5 min)
        """
        self.interval = interval_seconds
        self.running = False
        self.sync_count = 0
        self.last_sync_time = None
        self.error_count = 0

        # Database connection parameters
        self.db_params = {
            'host': os.getenv('DB_HOST', 'localhost'),
            'port': int(os.getenv('DB_PORT', 5432)),
            'database': os.getenv('DB_NAME', 'alex12060'),
            'user': os.getenv('DB_USER', 'alex12060_user'),
            'password': os.getenv('DB_PASSWORD', 'alex12060_pass')
        }

        # Google Sheets parameters
        self.spreadsheet_id = os.getenv('SPREADSHEET_ID')
        self.sa_json_path = os.getenv('GOOGLE_SA_JSON', 'google_sheets_credentials.json')

        # Initialize connections
        self.db_conn = None
        self.sheets_client = None
        self.spreadsheet = None

        # Rate limiter for Google Sheets API (40 requests per minute)
        self.rate_limiter = RateLimiter(max_requests=40, window_seconds=60)

        # Setup signal handlers for graceful shutdown
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)

        logger.info(f"PostgresSyncWorker initialized (interval: {interval_seconds}s)")

    def _signal_handler(self, signum, frame):
        """Handle shutdown signals."""
        logger.info(f"Received signal {signum}, shutting down gracefully...")
        self.running = False

    def _reconnect_db(self) -> bool:
        """Reconnect to PostgreSQL.

        Returns:
            True if successful, False otherwise
        """
        try:
            if self.db_conn and not self.db_conn.closed:
                try:
                    self.db_conn.close()
                except Exception:
                    pass
            self.db_conn = psycopg2.connect(**self.db_params)
            logger.info("Database reconnected successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to reconnect to database: {e}")
            return False

    def _ensure_db_connection(self) -> bool:
        """Ensure database connection is alive, reconnect if needed.

        Returns:
            True if connection is alive, False otherwise
        """
        if self.db_conn is None or self.db_conn.closed:
            logger.warning("Database connection lost, reconnecting...")
            return self._reconnect_db()
        return True

    def _init_connections(self) -> bool:
        """Initialize database and Google Sheets connections.

        Returns:
            True if successful, False otherwise
        """
        try:
            # Connect to PostgreSQL
            logger.info("Connecting to PostgreSQL...")
            self.db_conn = psycopg2.connect(**self.db_params)
            logger.info("PostgreSQL connection established")

            # Connect to Google Sheets
            logger.info("Connecting to Google Sheets...")
            scopes = ['https://www.googleapis.com/auth/spreadsheets']
            creds = Credentials.from_service_account_file(self.sa_json_path, scopes=scopes)
            self.sheets_client = gspread.authorize(creds)
            self.spreadsheet = self.sheets_client.open_by_key(self.spreadsheet_id)
            logger.info("Google Sheets connection established")

            return True

        except Exception as e:
            logger.error(f"Failed to initialize connections: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False

    def _get_pending_syncs(self) -> list:
        """Get all pending sync records from sync_queue.

        Returns:
            List of sync records (dicts)
        """
        try:
            # Ensure database connection is alive
            if not self._ensure_db_connection():
                return []

            with self.db_conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT id, table_name, record_id, operation, data, created_at
                    FROM sync_queue
                    WHERE status = 'pending'
                    ORDER BY created_at ASC
                    LIMIT 100
                """)
                return cur.fetchall()

        except Exception as e:
            logger.error(f"Failed to get pending syncs: {e}")
            return []

    def _sheets_api_call(self, func, *args, **kwargs):
        """Execute Google Sheets API call with rate limiting and retry.

        Args:
            func: The API function to call
            *args, **kwargs: Arguments to pass to the function

        Returns:
            Result of the API call
        """
        max_retries = 3
        base_delay = 30.0

        for attempt in range(max_retries + 1):
            # Wait if rate limit reached
            self.rate_limiter.wait_if_needed()

            try:
                return func(*args, **kwargs)
            except APIError as e:
                if e.response.status_code == 429:
                    if attempt < max_retries:
                        delay = base_delay * (2 ** attempt)
                        logger.warning(f"Quota exceeded (attempt {attempt + 1}/{max_retries + 1}), waiting {delay}s...")
                        time.sleep(delay)
                    else:
                        logger.error(f"Quota exceeded after {max_retries + 1} attempts")
                        raise
                else:
                    raise

    def _sync_shift(self, record_id: int, operation: str, data: dict):
        """Sync a shift record to Google Sheets.

        Args:
            record_id: Shift ID
            operation: INSERT, UPDATE, or DELETE
            data: Record data (JSONB from PostgreSQL)
        """
        try:
            # Get Shifts worksheet
            worksheet = self._sheets_api_call(self.spreadsheet.worksheet, 'Shifts')

            if operation == 'DELETE':
                # Find and delete row
                cell = self._sheets_api_call(worksheet.find, str(record_id), in_column=1)
                if cell:
                    self._sheets_api_call(worksheet.delete_rows, cell.row)
                    logger.info(f"Deleted shift {record_id} from Google Sheets")
                return

            # For INSERT/UPDATE, get the full shift data from PostgreSQL
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
                        s.total_per_hour,
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
                shift = cur.fetchone()

            if not shift:
                logger.warning(f"Shift {record_id} not found in database")
                return

            # Format row data for Google Sheets (19 columns, Models at the end)
            # Columns: ID, Date, EmployeeID, EmployeeName, ClockIn, ClockOut, WorkedHours,
            #          TotalSales, NetSales, CommissionPct, TotalHourly, Commissions, TotalMade,
            #          RollingAverage, BonusCounter, ModelA, ModelB, ModelC, ModelD
            row_data = [
                shift['id'],                                                              # A: ID
                shift['date'].strftime('%Y-%m-%d %H:%M:%S') if shift['date'] else '',     # B: Date
                shift['employee_id'],                                                     # C: EmployeeID
                shift['employee_name'],                                                   # D: EmployeeName
                shift['clock_in'].strftime('%Y-%m-%d %H:%M:%S') if shift['clock_in'] else '',   # E: ClockIn
                shift['clock_out'].strftime('%Y-%m-%d %H:%M:%S') if shift['clock_out'] else '', # F: ClockOut
                float(shift['worked_hours']) if shift['worked_hours'] else 0,             # G: WorkedHours
                float(shift['total_sales']) if shift['total_sales'] else 0,               # H: TotalSales
                float(shift['net_sales']) if shift['net_sales'] else 0,                   # I: NetSales
                float(shift['commission_pct']) if shift['commission_pct'] else 0,         # J: CommissionPct
                float(shift['total_per_hour']) if shift['total_per_hour'] else 0,         # K: TotalHourly
                float(shift['commissions']) if shift['commissions'] else 0,               # L: Commissions
                float(shift['total_made']) if shift['total_made'] else 0,                 # M: TotalMade
                float(shift['rolling_average']) if shift['rolling_average'] else 0,       # N: RollingAverage
                'TRUE' if shift['bonus_counter'] else 'FALSE',                            # O: BonusCounter
                float(shift['model_a']) if shift['model_a'] else 0,                       # P: ModelA
                float(shift['model_b']) if shift['model_b'] else 0,                       # Q: ModelB
                float(shift['model_c']) if shift['model_c'] else 0,                       # R: ModelC
                float(shift['model_d']) if shift['model_d'] else 0,                       # S: ModelD
            ]

            # Check if row exists
            try:
                cell = self._sheets_api_call(worksheet.find, str(record_id), in_column=1)
                if cell:
                    # Update existing row (19 columns: A to S)
                    self._sheets_api_call(worksheet.update, f'A{cell.row}:S{cell.row}', [row_data])
                    logger.info(f"Updated shift {record_id} in Google Sheets")
                else:
                    # Append new row
                    self._sheets_api_call(worksheet.append_row, row_data)
                    logger.info(f"Inserted shift {record_id} to Google Sheets")
            except gspread.exceptions.CellNotFound:
                # Append new row
                self._sheets_api_call(worksheet.append_row, row_data)
                logger.info(f"Inserted shift {record_id} to Google Sheets")

        except Exception as e:
            logger.error(f"Failed to sync shift {record_id}: {e}")
            import traceback
            logger.error(traceback.format_exc())
            raise

    def _sync_active_bonus(self, record_id: int, operation: str, data: dict):
        """Sync an active bonus record to Google Sheets.

        Args:
            record_id: Bonus ID
            operation: INSERT, UPDATE, or DELETE
            data: Record data (JSONB from PostgreSQL)
        """
        try:
            worksheet = self._sheets_api_call(self.spreadsheet.worksheet, 'ActiveBonuses')

            if operation == 'DELETE':
                # Find and delete row
                cell = self._sheets_api_call(worksheet.find, str(record_id), in_column=1)
                if cell:
                    self._sheets_api_call(worksheet.delete_rows, cell.row)
                    logger.info(f"Deleted active bonus {record_id} from Google Sheets")
                return

            # For INSERT/UPDATE, get the full data from PostgreSQL
            with self.db_conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT id, employee_id, bonus_type, value, applied, shift_id, created_at
                    FROM active_bonuses
                    WHERE id = %s
                """, (record_id,))
                bonus = cur.fetchone()

            if not bonus:
                logger.warning(f"Active bonus {record_id} not found in database")
                return

            # Format row data
            row_data = [
                bonus['id'],
                bonus['employee_id'],
                bonus['bonus_type'],
                float(bonus['value']) if bonus['value'] else 0,
                'TRUE' if bonus['applied'] else 'FALSE',
                bonus['shift_id'] if bonus['shift_id'] else '',
                bonus['created_at'].strftime('%Y-%m-%d %H:%M:%S') if bonus['created_at'] else ''
            ]

            # Check if row exists
            try:
                cell = self._sheets_api_call(worksheet.find, str(record_id), in_column=1)
                if cell:
                    # Update existing row
                    self._sheets_api_call(worksheet.update, f'A{cell.row}:G{cell.row}', [row_data])
                    logger.info(f"Updated active bonus {record_id} in Google Sheets")
                else:
                    # Append new row
                    self._sheets_api_call(worksheet.append_row, row_data)
                    logger.info(f"Inserted active bonus {record_id} to Google Sheets")
            except gspread.exceptions.CellNotFound:
                # Append new row
                self._sheets_api_call(worksheet.append_row, row_data)
                logger.info(f"Inserted active bonus {record_id} to Google Sheets")

        except Exception as e:
            logger.error(f"Failed to sync active bonus {record_id}: {e}")
            import traceback
            logger.error(traceback.format_exc())
            raise

    def _sync_employee_rank(self, record_id: int, operation: str, data: dict):
        """Sync an employee rank record to Google Sheets.

        Args:
            record_id: Employee rank ID
            operation: INSERT, UPDATE, or DELETE
            data: Record data (JSONB from PostgreSQL)
        """
        try:
            worksheet = self._sheets_api_call(self.spreadsheet.worksheet, 'EmployeeRanks')

            if operation == 'DELETE':
                # Find and delete row
                cell = self._sheets_api_call(worksheet.find, str(record_id), in_column=1)
                if cell:
                    self._sheets_api_call(worksheet.delete_rows, cell.row)
                    logger.info(f"Deleted employee rank {record_id} from Google Sheets")
                return

            # For INSERT/UPDATE, get the full data from PostgreSQL
            with self.db_conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT
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
                rank = cur.fetchone()

            if not rank:
                logger.warning(f"Employee rank {record_id} not found in database")
                return

            # Format row data
            row_data = [
                rank['employee_id'],
                rank['year'],
                rank['month'],
                rank['current_rank'] if rank['current_rank'] else '',
                rank['previous_rank'] if rank['previous_rank'] else '',
                rank['updated_at'].strftime('%Y-%m-%d %H:%M:%S') if rank['updated_at'] else '',
                'TRUE' if rank['notified'] else 'FALSE'
            ]

            # Find by employee_id, year, month (composite key)
            all_values = self._sheets_api_call(worksheet.get_all_values)
            found_row = None
            for idx, row in enumerate(all_values[1:], start=2):  # Skip header
                if (len(row) >= 3 and
                    str(row[0]) == str(rank['employee_id']) and
                    str(row[1]) == str(rank['year']) and
                    str(row[2]) == str(rank['month'])):
                    found_row = idx
                    break

            if found_row:
                # Update existing row
                self._sheets_api_call(worksheet.update, f'A{found_row}:G{found_row}', [row_data])
                logger.info(f"Updated employee rank {record_id} in Google Sheets")
            else:
                # Append new row
                self._sheets_api_call(worksheet.append_row, row_data)
                logger.info(f"Inserted employee rank {record_id} to Google Sheets")

        except Exception as e:
            logger.error(f"Failed to sync employee rank {record_id}: {e}")
            import traceback
            logger.error(traceback.format_exc())
            raise

    def _sync_employee(self, record_id: int, operation: str, data: dict):
        """Sync an employee record to Google Sheets EmployeeSettings.

        Args:
            record_id: Employee ID
            operation: INSERT, UPDATE, or DELETE
            data: Record data (JSONB from PostgreSQL)
        """
        try:
            worksheet = self._sheets_api_call(self.spreadsheet.worksheet, 'EmployeeSettings')

            if operation == 'DELETE':
                # Find and delete row by employee ID
                cell = self._sheets_api_call(worksheet.find, str(record_id), in_column=1)
                if cell:
                    self._sheets_api_call(worksheet.delete_rows, cell.row)
                    logger.info(f"Deleted employee {record_id} from Google Sheets")
                return

            # For INSERT/UPDATE, get the full data from PostgreSQL
            with self.db_conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT id, name, telegram_id, is_active, hourly_wage, sales_commission
                    FROM employees
                    WHERE id = %s
                """, (record_id,))
                employee = cur.fetchone()

            if not employee:
                logger.warning(f"Employee {record_id} not found in database")
                return

            # Format row data for EmployeeSettings worksheet
            # Columns: EmployeeID, EmployeeName, Hourly wage, Sales commission, Active
            row_data = [
                employee['id'],
                employee['name'],
                float(employee['hourly_wage']) if employee['hourly_wage'] else 15.0,
                float(employee['sales_commission']) if employee['sales_commission'] else 8.0,
                'TRUE' if employee['is_active'] else 'FALSE'
            ]

            # Check if row exists
            try:
                cell = self._sheets_api_call(worksheet.find, str(record_id), in_column=1)
                if cell:
                    # Update existing row
                    self._sheets_api_call(worksheet.update, f'A{cell.row}:E{cell.row}', [row_data])
                    logger.info(f"Updated employee {record_id} in Google Sheets")
                else:
                    # Append new row
                    self._sheets_api_call(worksheet.append_row, row_data)
                    logger.info(f"Inserted employee {record_id} to Google Sheets")
            except gspread.exceptions.CellNotFound:
                # Append new row
                self._sheets_api_call(worksheet.append_row, row_data)
                logger.info(f"Inserted employee {record_id} to Google Sheets")

        except Exception as e:
            logger.error(f"Failed to sync employee {record_id}: {e}")
            import traceback
            logger.error(traceback.format_exc())
            raise

    def _mark_synced(self, sync_id: int):
        """Mark a sync record as synced.

        Args:
            sync_id: Sync queue record ID
        """
        try:
            with self.db_conn.cursor() as cur:
                cur.execute("""
                    UPDATE sync_queue
                    SET status = 'completed', processed_at = NOW()
                    WHERE id = %s
                """, (sync_id,))
            self.db_conn.commit()

        except Exception as e:
            logger.error(f"Failed to mark sync {sync_id} as synced: {e}")
            self.db_conn.rollback()

    def _mark_failed(self, sync_id: int, error_message: str):
        """Mark a sync record as failed.

        Args:
            sync_id: Sync queue record ID
            error_message: Error message
        """
        try:
            with self.db_conn.cursor() as cur:
                cur.execute("""
                    UPDATE sync_queue
                    SET status = 'failed',
                        error_message = %s,
                        processed_at = NOW()
                    WHERE id = %s
                """, (error_message[:500], sync_id))  # Limit error message length
            self.db_conn.commit()

        except Exception as e:
            logger.error(f"Failed to mark sync {sync_id} as failed: {e}")
            self.db_conn.rollback()

    def _perform_sync(self) -> bool:
        """Perform one sync cycle.

        Returns:
            True if successful, False otherwise
        """
        try:
            logger.info("=" * 70)
            logger.info(f"Starting sync cycle #{self.sync_count + 1}")
            logger.info("=" * 70)

            start_time = time.time()

            # Get pending syncs
            pending_syncs = self._get_pending_syncs()
            logger.info(f"Found {len(pending_syncs)} pending sync records")

            if not pending_syncs:
                logger.info("No pending syncs, skipping")
                self.sync_count += 1
                self.last_sync_time = datetime.now()
                return True

            # Process each sync
            synced_count = 0
            failed_count = 0

            for sync_record in pending_syncs:
                try:
                    table_name = sync_record['table_name']
                    record_id = sync_record['record_id']
                    operation = sync_record['operation']
                    data = sync_record['data']

                    logger.info(f"Syncing {table_name} {record_id} ({operation})")

                    # Route to appropriate sync method
                    if table_name == 'shifts':
                        self._sync_shift(record_id, operation, data)
                    elif table_name == 'active_bonuses':
                        self._sync_active_bonus(record_id, operation, data)
                    elif table_name == 'employee_ranks':
                        self._sync_employee_rank(record_id, operation, data)
                    elif table_name == 'employees':
                        self._sync_employee(record_id, operation, data)
                    else:
                        logger.warning(f"Unknown table: {table_name}")
                        continue

                    # Mark as synced
                    self._mark_synced(sync_record['id'])
                    synced_count += 1

                except Exception as e:
                    logger.error(f"Failed to sync record {sync_record['id']}: {e}")
                    self._mark_failed(sync_record['id'], str(e))
                    failed_count += 1

            # Calculate duration
            duration = time.time() - start_time

            # Update stats
            self.sync_count += 1
            self.last_sync_time = datetime.now()
            self.error_count = 0  # Reset error count on success

            logger.info("=" * 70)
            logger.info(f"Sync cycle #{self.sync_count} completed in {duration:.2f}s")
            logger.info(f"Synced: {synced_count}, Failed: {failed_count}")
            logger.info("=" * 70)

            return True

        except Exception as e:
            logger.error(f"Sync cycle failed: {e}")
            self.error_count += 1

            # Log traceback for debugging
            import traceback
            logger.error(traceback.format_exc())

            return False

    def run_once(self) -> int:
        """Run sync once and exit.

        Returns:
            Exit code (0 = success, 1 = failure)
        """
        logger.info("Running sync worker in ONCE mode")

        # Initialize connections
        if not self._init_connections():
            logger.error("Connection initialization failed")
            return 1

        # Perform sync
        success = self._perform_sync()

        # Close connections
        if self.db_conn:
            self.db_conn.close()

        if success:
            logger.info("Sync completed successfully")
            return 0
        else:
            logger.error("Sync failed")
            return 1

    def run_continuous(self) -> int:
        """Run sync worker continuously.

        Returns:
            Exit code (0 = clean shutdown, 1 = error)
        """
        logger.info("=" * 70)
        logger.info("SYNC WORKER STARTING")
        logger.info("=" * 70)
        logger.info(f"Mode: CONTINUOUS")
        logger.info(f"Interval: {self.interval} seconds")
        logger.info(f"Database: {self.db_params['database']}")
        logger.info(f"Spreadsheet ID: {self.spreadsheet_id}")
        logger.info("=" * 70)

        # Initialize connections
        if not self._init_connections():
            logger.error("Connection initialization failed, exiting")
            return 1

        # Perform initial sync
        logger.info("Performing initial sync...")
        self._perform_sync()

        # Start continuous loop
        self.running = True
        logger.info("Entering continuous sync loop...")
        logger.info(f"Next sync in {self.interval} seconds")

        while self.running:
            try:
                # Sleep until next sync
                sleep_start = time.time()
                while self.running and (time.time() - sleep_start) < self.interval:
                    time.sleep(1)

                if not self.running:
                    break

                # Perform sync
                self._perform_sync()

                # Check error count
                if self.error_count >= 5:
                    logger.error(f"Too many consecutive errors ({self.error_count}), exiting")
                    return 1

                # Log next sync time
                if self.running:
                    next_sync = datetime.now().timestamp() + self.interval
                    next_sync_str = datetime.fromtimestamp(next_sync).strftime('%H:%M:%S')
                    logger.info(f"Next sync at {next_sync_str} ({self.interval}s)")

            except Exception as e:
                logger.error(f"Unexpected error in main loop: {e}")
                import traceback
                logger.error(traceback.format_exc())
                self.error_count += 1

                if self.error_count >= 5:
                    logger.error(f"Too many errors ({self.error_count}), exiting")
                    return 1

        # Close connections
        if self.db_conn:
            self.db_conn.close()

        # Clean shutdown
        logger.info("=" * 70)
        logger.info("SYNC WORKER SHUTTING DOWN")
        logger.info("=" * 70)
        logger.info(f"Total sync cycles: {self.sync_count}")
        logger.info(f"Last sync: {self.last_sync_time}")
        logger.info("=" * 70)

        return 0


def main():
    """Main entry point."""
    # Load environment variables from .env if available
    env_path = Path('/opt/alex12060-bot/.env')
    if env_path.exists():
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    os.environ[key] = value

    parser = argparse.ArgumentParser(
        description='PostgreSQL to Google Sheets sync worker'
    )

    parser.add_argument(
        '--interval',
        type=int,
        default=300,
        help='Sync interval in seconds (default: 300 = 5 minutes)'
    )

    parser.add_argument(
        '--once',
        action='store_true',
        help='Run sync once and exit (for testing)'
    )

    args = parser.parse_args()

    # Create worker
    worker = PostgresSyncWorker(interval_seconds=args.interval)

    # Run
    if args.once:
        exit_code = worker.run_once()
    else:
        exit_code = worker.run_continuous()

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
