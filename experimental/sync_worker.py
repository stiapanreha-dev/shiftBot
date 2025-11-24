#!/usr/bin/env python3
"""Standalone sync worker for bidirectional synchronization.

This script runs as a separate systemd service and handles periodic
synchronization between SQLite (local) and Google Sheets (remote).

It is independent from the main bot process and can be restarted
without affecting the bot.

Usage:
    python3 sync_worker.py [--interval SECONDS] [--once]

Author: Claude Code (PROMPT 3.3 - Systemd Service for Sync Worker)
Date: 2025-11-11
Version: 1.0.0
"""

import logging
import signal
import sys
import time
import argparse
from datetime import datetime
from pathlib import Path

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('sync_worker.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Import our modules
try:
    from sheets_service import SheetsService
    from sync_manager import SyncManager
    from database_schema import DatabaseSchema
except ImportError as e:
    logger.error(f"Failed to import required modules: {e}")
    logger.error("Make sure you're running from the correct directory")
    sys.exit(1)


class StandaloneSyncWorker:
    """Standalone sync worker that runs as systemd service."""

    def __init__(self, interval_seconds: int = 300, db_path: str = "data/reference_data.db"):
        """Initialize sync worker.

        Args:
            interval_seconds: Sync interval in seconds (default: 300 = 5 min)
            db_path: Path to SQLite database
        """
        self.interval = interval_seconds
        self.db_path = db_path
        self.running = False
        self.sync_count = 0
        self.last_sync_time = None
        self.error_count = 0

        # Setup signal handlers for graceful shutdown
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)

        logger.info(f"StandaloneSyncWorker initialized (interval: {interval_seconds}s)")

    def _signal_handler(self, signum, frame):
        """Handle shutdown signals."""
        logger.info(f"Received signal {signum}, shutting down gracefully...")
        self.running = False

    def _init_database(self) -> bool:
        """Initialize database schema if needed.

        Returns:
            True if successful, False otherwise
        """
        try:
            # Ensure data directory exists
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)

            # Initialize schema
            schema = DatabaseSchema(self.db_path)
            schema.init_schema()

            logger.info("Database schema initialized")
            return True

        except Exception as e:
            logger.error(f"Failed to initialize database: {e}")
            return False

    def _perform_sync(self, sync_manager: SyncManager) -> bool:
        """Perform one sync cycle.

        Args:
            sync_manager: SyncManager instance

        Returns:
            True if successful, False otherwise
        """
        try:
            logger.info("=" * 70)
            logger.info(f"Starting sync cycle #{self.sync_count + 1}")
            logger.info("=" * 70)

            start_time = time.time()

            # Pull from Sheets
            logger.info("Pulling changes from Google Sheets...")
            pull_counts = sync_manager.full_sync_from_sheets()
            logger.info(f"Pull completed: {pull_counts}")

            # Push to Sheets (if any pending changes)
            logger.info("Pushing changes to Google Sheets...")
            push_counts = sync_manager.push_changes_to_sheets()

            if any(push_counts.values()):
                logger.info(f"Push completed: {push_counts}")
            else:
                logger.info("No pending changes to push")

            # Calculate duration
            duration = time.time() - start_time

            # Update stats
            self.sync_count += 1
            self.last_sync_time = datetime.now()
            self.error_count = 0  # Reset error count on success

            # Get sync stats
            stats = sync_manager.get_sync_stats()

            logger.info("=" * 70)
            logger.info(f"Sync cycle #{self.sync_count} completed in {duration:.2f}s")
            logger.info(f"Stats: {stats}")
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

        # Initialize database
        if not self._init_database():
            logger.error("Database initialization failed")
            return 1

        # Initialize services
        try:
            sheets_service = SheetsService()
            sync_manager = SyncManager(sheets_service, db_path=self.db_path)
        except Exception as e:
            logger.error(f"Failed to initialize services: {e}")
            return 1

        # Perform sync
        success = self._perform_sync(sync_manager)

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
        logger.info(f"Database: {self.db_path}")
        logger.info("=" * 70)

        # Initialize database
        if not self._init_database():
            logger.error("Database initialization failed, exiting")
            return 1

        # Initialize services
        try:
            logger.info("Initializing Google Sheets service...")
            sheets_service = SheetsService()

            logger.info("Initializing sync manager...")
            sync_manager = SyncManager(sheets_service, db_path=self.db_path)

            logger.info("Services initialized successfully")

        except Exception as e:
            logger.error(f"Failed to initialize services: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return 1

        # Perform initial sync
        logger.info("Performing initial sync...")
        self._perform_sync(sync_manager)

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
                self._perform_sync(sync_manager)

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
    parser = argparse.ArgumentParser(
        description='Standalone sync worker for bidirectional synchronization'
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

    parser.add_argument(
        '--db-path',
        type=str,
        default='data/reference_data.db',
        help='Path to SQLite database (default: data/reference_data.db)'
    )

    args = parser.parse_args()

    # Create worker
    worker = StandaloneSyncWorker(
        interval_seconds=args.interval,
        db_path=args.db_path
    )

    # Run
    if args.once:
        exit_code = worker.run_once()
    else:
        exit_code = worker.run_continuous()

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
