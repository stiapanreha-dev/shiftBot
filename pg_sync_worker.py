#!/usr/bin/env python3
"""PostgreSQL-to-Google Sheets sync worker.

This script processes the sync_queue table and synchronizes changes from
PostgreSQL to Google Sheets.

It runs as a separate systemd service and handles periodic synchronization.

Usage:
    python3 pg_sync_worker.py [--interval SECONDS] [--once]

Author: Claude Code (PostgreSQL sync worker)
Date: 2025-12-12
Version: 1.2.0 (added rate limiting)
"""

import logging
import signal
import sys
import time
import argparse
import os
from collections import deque
from datetime import datetime
from functools import wraps
from pathlib import Path
import psycopg2
from psycopg2.extras import RealDictCursor
import gspread
from gspread.exceptions import APIError
from google.oauth2.service_account import Credentials

from services.sync import (
    ShiftSyncProcessor,
    BonusSyncProcessor,
    RankSyncProcessor,
    EmployeeSyncProcessor,
    FortnightSyncProcessor,
)

# Setup logging
# Use LOG_DIR env var, or 'logs' relative to script location
log_dir = Path(os.getenv('LOG_DIR', Path(__file__).parent / 'logs'))
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


# Global rate limiter instance
rate_limiter = RateLimiter()


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

        # Sync processors (initialized after connections)
        self.processors = {}

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

            # Initialize sync processors
            self._init_processors()

            return True

        except Exception as e:
            logger.error(f"Failed to initialize connections: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False

    def _init_processors(self):
        """Initialize sync processors for each table."""
        self.processors = {
            'shifts': ShiftSyncProcessor(self.spreadsheet, self.db_conn),
            'active_bonuses': BonusSyncProcessor(self.spreadsheet, self.db_conn),
            'employee_ranks': RankSyncProcessor(self.spreadsheet, self.db_conn),
            'employees': EmployeeSyncProcessor(self.spreadsheet, self.db_conn),
            'employee_fortnights': FortnightSyncProcessor(self.spreadsheet, self.db_conn),
        }
        logger.info(f"Initialized {len(self.processors)} sync processors")

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

                    # Route to appropriate processor
                    processor = self.processors.get(table_name)
                    if processor:
                        # Apply rate limiting before each sync operation
                        rate_limiter.wait_if_needed()
                        processor.process(record_id, operation, data)
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
    # Load .env from script directory or ENV_FILE path
    env_path = Path(os.getenv('ENV_FILE', Path(__file__).parent / '.env'))
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
