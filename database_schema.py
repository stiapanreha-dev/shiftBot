"""SQLite database schema for reference tables.

This module defines the schema for local SQLite storage of reference data
(справочники) that will be synchronized bidirectionally with Google Sheets.

Author: Claude Code (PROMPT 3.2 - Bidirectional Sync)
Date: 2025-11-11
Version: 1.0.0
"""

import sqlite3
import logging
from typing import Optional
from pathlib import Path

logger = logging.getLogger(__name__)


class DatabaseSchema:
    """Manages SQLite database schema for reference tables."""

    # Database version for migrations
    SCHEMA_VERSION = 1

    def __init__(self, db_path: str = "data/reference_data.db"):
        """Initialize database schema manager.

        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = db_path

        # Ensure data directory exists
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)

        logger.info(f"Database schema manager initialized: {db_path}")

    def get_connection(self) -> sqlite3.Connection:
        """Get database connection.

        Returns:
            SQLite connection object
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row  # Enable dict-like access
        return conn

    def init_schema(self) -> None:
        """Initialize database schema (create tables if not exist)."""
        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            # ==================== Metadata Table ====================
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS _schema_metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Store schema version
            cursor.execute("""
                INSERT OR REPLACE INTO _schema_metadata (key, value)
                VALUES ('schema_version', ?)
            """, (str(self.SCHEMA_VERSION),))

            # ==================== EmployeeSettings Table ====================
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS employee_settings (
                    employee_id INTEGER PRIMARY KEY,
                    hourly_wage REAL NOT NULL DEFAULT 15.0,
                    sales_commission REAL NOT NULL DEFAULT 8.0,

                    -- Sync metadata
                    last_synced_at TIMESTAMP,
                    last_modified_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    source TEXT DEFAULT 'sheets',  -- 'sheets' or 'local'
                    sync_status TEXT DEFAULT 'synced',  -- 'synced', 'pending', 'conflict'
                    version INTEGER DEFAULT 1
                )
            """)

            # Index for quick lookup
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_employee_settings_sync
                ON employee_settings(sync_status, last_modified_at)
            """)

            # ==================== DynamicRates Table ====================
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS dynamic_rates (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    min_amount REAL NOT NULL,
                    max_amount REAL NOT NULL,
                    percentage REAL NOT NULL,

                    -- Sync metadata
                    last_synced_at TIMESTAMP,
                    last_modified_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    source TEXT DEFAULT 'sheets',
                    sync_status TEXT DEFAULT 'synced',
                    version INTEGER DEFAULT 1,

                    -- Constraint
                    CHECK (min_amount <= max_amount),
                    CHECK (percentage >= 0 AND percentage <= 100)
                )
            """)

            # Index for quick range lookup
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_dynamic_rates_range
                ON dynamic_rates(min_amount, max_amount)
            """)

            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_dynamic_rates_sync
                ON dynamic_rates(sync_status, last_modified_at)
            """)

            # ==================== Ranks Table ====================
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS ranks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    rank_name TEXT NOT NULL UNIQUE,
                    min_amount REAL NOT NULL,
                    max_amount REAL NOT NULL,
                    bonus_1 TEXT,
                    bonus_2 TEXT,
                    bonus_3 TEXT,
                    text TEXT,  -- Rank description/message

                    -- Sync metadata
                    last_synced_at TIMESTAMP,
                    last_modified_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    source TEXT DEFAULT 'sheets',
                    sync_status TEXT DEFAULT 'synced',
                    version INTEGER DEFAULT 1,

                    -- Constraint
                    CHECK (min_amount <= max_amount)
                )
            """)

            # Index for quick lookup
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_ranks_name
                ON ranks(rank_name)
            """)

            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_ranks_range
                ON ranks(min_amount, max_amount)
            """)

            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_ranks_sync
                ON ranks(sync_status, last_modified_at)
            """)

            # ==================== Sync Log Table ====================
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS sync_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    table_name TEXT NOT NULL,
                    operation TEXT NOT NULL,  -- 'pull', 'push', 'conflict'
                    record_id TEXT NOT NULL,
                    status TEXT NOT NULL,  -- 'success', 'failed', 'conflict'
                    error_message TEXT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Index for log queries
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_sync_log_table_time
                ON sync_log(table_name, timestamp DESC)
            """)

            conn.commit()
            logger.info("Database schema initialized successfully")

        except sqlite3.Error as e:
            conn.rollback()
            logger.error(f"Failed to initialize schema: {e}")
            raise
        finally:
            conn.close()

    def drop_all_tables(self) -> None:
        """Drop all tables (for testing/reset)."""
        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("DROP TABLE IF EXISTS employee_settings")
            cursor.execute("DROP TABLE IF EXISTS dynamic_rates")
            cursor.execute("DROP TABLE IF EXISTS ranks")
            cursor.execute("DROP TABLE IF EXISTS sync_log")
            cursor.execute("DROP TABLE IF EXISTS _schema_metadata")
            conn.commit()
            logger.info("All tables dropped")
        except sqlite3.Error as e:
            conn.rollback()
            logger.error(f"Failed to drop tables: {e}")
            raise
        finally:
            conn.close()

    def get_schema_version(self) -> int:
        """Get current schema version from database.

        Returns:
            Schema version number or 0 if not found
        """
        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("""
                SELECT value FROM _schema_metadata WHERE key = 'schema_version'
            """)
            row = cursor.fetchone()
            return int(row[0]) if row else 0
        except sqlite3.Error:
            return 0
        finally:
            conn.close()

    def vacuum(self) -> None:
        """Optimize database (reclaim space)."""
        conn = self.get_connection()
        try:
            conn.execute("VACUUM")
            logger.info("Database vacuumed")
        except sqlite3.Error as e:
            logger.error(f"Failed to vacuum database: {e}")
            raise
        finally:
            conn.close()


# ==================== Helper Functions ====================

def get_db_connection(db_path: str = "data/reference_data.db") -> sqlite3.Connection:
    """Get database connection with row factory.

    Args:
        db_path: Path to database file

    Returns:
        SQLite connection
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


# ==================== Main (for testing) ====================

if __name__ == "__main__":
    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # Initialize schema
    schema = DatabaseSchema("data/reference_data.db")

    print("Initializing database schema...")
    schema.init_schema()

    print(f"Schema version: {schema.get_schema_version()}")
    print("Database schema initialized successfully!")
