"""PostgreSQL Database Schema for Alex12060 Bot.

This module defines the complete database schema for the bot, including:
- Transactional tables: shifts, active_bonuses
- Reference tables: employee_settings, dynamic_rates, ranks, employee_ranks
- Metadata tables: schema_metadata, sync_log

Architecture:
    PostgreSQL serves as the primary database, replacing Google Sheets.
    All reads and writes go through PostgreSQL for maximum performance.
    Optional sync with Google Sheets for backup/reporting.

Author: Claude Code (PROMPT 4.1 - PostgreSQL Migration)
Date: 2025-11-11
Version: 3.0.0
"""

import logging
import psycopg2
from psycopg2 import sql, extras
from typing import Optional, Dict, Any, List
from datetime import datetime
import os

logger = logging.getLogger(__name__)


class PostgresSchema:
    """PostgreSQL schema manager for Alex12060 bot."""

    SCHEMA_VERSION = 1

    def __init__(
        self,
        host: str = "localhost",
        port: int = 5432,
        database: str = "alex12060",
        user: str = "lexun",
        password: Optional[str] = None
    ):
        """Initialize PostgreSQL schema manager.

        Args:
            host: PostgreSQL host (default: localhost)
            port: PostgreSQL port (default: 5432)
            database: Database name (default: alex12060)
            user: Database user (default: lexun)
            password: Database password (from env if not provided)
        """
        self.host = host
        self.port = port
        self.database = database
        self.user = user
        self.password = password or os.getenv("POSTGRES_PASSWORD", "")

        logger.info(f"PostgresSchema initialized: {user}@{host}:{port}/{database}")

    def get_connection(self) -> psycopg2.extensions.connection:
        """Create a new PostgreSQL connection.

        Returns:
            psycopg2 connection object
        """
        return psycopg2.connect(
            host=self.host,
            port=self.port,
            database=self.database,
            user=self.user,
            password=self.password,
            cursor_factory=extras.RealDictCursor
        )

    def init_schema(self) -> None:
        """Initialize the complete database schema.

        Creates all tables if they don't exist:
        - schema_metadata
        - employee_settings
        - dynamic_rates
        - ranks
        - employee_ranks
        - shifts
        - active_bonuses
        - sync_log
        """
        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            logger.info("Initializing PostgreSQL schema...")

            # 1. Schema metadata table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS schema_metadata (
                    key VARCHAR(255) PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            logger.info("✓ schema_metadata table created")

            # 2. Employee settings (reference data)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS employee_settings (
                    employee_id INTEGER PRIMARY KEY,
                    employee_name VARCHAR(255) NOT NULL,
                    base_commission_pct DECIMAL(5, 2) NOT NULL,
                    active BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_employee_active
                ON employee_settings(active)
            """)
            logger.info("✓ employee_settings table created")

            # 3. Dynamic rates (reference data)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS dynamic_rates (
                    id SERIAL PRIMARY KEY,
                    min_sales DECIMAL(10, 2) NOT NULL,
                    max_sales DECIMAL(10, 2),
                    rate_pct DECIMAL(5, 2) NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    CONSTRAINT check_sales_range CHECK (
                        max_sales IS NULL OR max_sales >= min_sales
                    )
                )
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_dynamic_rates_range
                ON dynamic_rates(min_sales, max_sales)
            """)
            logger.info("✓ dynamic_rates table created")

            # 4. Ranks (reference data)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS ranks (
                    id SERIAL PRIMARY KEY,
                    rank_name VARCHAR(255) NOT NULL UNIQUE,
                    bonus_pct DECIMAL(5, 2) NOT NULL,
                    min_total_sales DECIMAL(10, 2),
                    min_days_worked INTEGER,
                    description TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            logger.info("✓ ranks table created")

            # 5. Employee ranks (reference data - monthly)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS employee_ranks (
                    id SERIAL PRIMARY KEY,
                    employee_id INTEGER NOT NULL,
                    month VARCHAR(7) NOT NULL,
                    rank_id INTEGER REFERENCES ranks(id),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(employee_id, month)
                )
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_employee_ranks_lookup
                ON employee_ranks(employee_id, month)
            """)
            logger.info("✓ employee_ranks table created")

            # 6. Shifts (transactional data - MAIN TABLE)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS shifts (
                    shift_id SERIAL PRIMARY KEY,
                    employee_id INTEGER NOT NULL REFERENCES employee_settings(employee_id),
                    employee_name VARCHAR(255) NOT NULL,
                    shift_date DATE NOT NULL,
                    time_in TIME NOT NULL,
                    time_out TIME,
                    total_hours DECIMAL(5, 2),

                    -- Product sales
                    bella_sales DECIMAL(10, 2) DEFAULT 0,
                    laura_sales DECIMAL(10, 2) DEFAULT 0,
                    sophie_sales DECIMAL(10, 2) DEFAULT 0,
                    alice_sales DECIMAL(10, 2) DEFAULT 0,
                    emma_sales DECIMAL(10, 2) DEFAULT 0,
                    molly_sales DECIMAL(10, 2) DEFAULT 0,
                    total_sales DECIMAL(10, 2) DEFAULT 0,

                    -- Commission breakdown
                    base_commission_pct DECIMAL(5, 2),
                    dynamic_commission_pct DECIMAL(5, 2) DEFAULT 0,
                    bonus_commission_pct DECIMAL(5, 2) DEFAULT 0,
                    total_commission_pct DECIMAL(5, 2),
                    commission_amount DECIMAL(10, 2),

                    -- Status
                    status VARCHAR(50) DEFAULT 'active',

                    -- Metadata
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

                    -- Indexes for common queries
                    CONSTRAINT check_time_out CHECK (
                        time_out IS NULL OR time_out >= time_in
                    )
                )
            """)

            # Indexes for shifts table (most queried table)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_shifts_employee
                ON shifts(employee_id)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_shifts_date
                ON shifts(shift_date DESC)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_shifts_employee_date
                ON shifts(employee_id, shift_date DESC)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_shifts_status
                ON shifts(status)
            """)
            logger.info("✓ shifts table created with indexes")

            # 7. Active bonuses (transactional data)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS active_bonuses (
                    id SERIAL PRIMARY KEY,
                    shift_id INTEGER NOT NULL REFERENCES shifts(shift_id) ON DELETE CASCADE,
                    bonus_type VARCHAR(255) NOT NULL,
                    bonus_pct DECIMAL(5, 2) NOT NULL,
                    reason TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(shift_id, bonus_type)
                )
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_active_bonuses_shift
                ON active_bonuses(shift_id)
            """)
            logger.info("✓ active_bonuses table created")

            # 8. Sync log (metadata for Google Sheets sync)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS sync_log (
                    id SERIAL PRIMARY KEY,
                    sync_type VARCHAR(50) NOT NULL,
                    direction VARCHAR(10) NOT NULL,
                    table_name VARCHAR(255) NOT NULL,
                    records_affected INTEGER DEFAULT 0,
                    status VARCHAR(50) NOT NULL,
                    error_message TEXT,
                    started_at TIMESTAMP NOT NULL,
                    completed_at TIMESTAMP,
                    duration_seconds DECIMAL(10, 2)
                )
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_sync_log_type
                ON sync_log(sync_type, started_at DESC)
            """)
            logger.info("✓ sync_log table created")

            # Set schema version
            cursor.execute("""
                INSERT INTO schema_metadata (key, value, updated_at)
                VALUES ('schema_version', %s, CURRENT_TIMESTAMP)
                ON CONFLICT (key) DO UPDATE
                SET value = EXCLUDED.value, updated_at = CURRENT_TIMESTAMP
            """, (str(self.SCHEMA_VERSION),))

            cursor.execute("""
                INSERT INTO schema_metadata (key, value, updated_at)
                VALUES ('initialized_at', %s, CURRENT_TIMESTAMP)
                ON CONFLICT (key) DO NOTHING
            """, (datetime.now().isoformat(),))

            conn.commit()
            logger.info(f"✅ PostgreSQL schema initialized (version {self.SCHEMA_VERSION})")

        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to initialize schema: {e}")
            raise
        finally:
            cursor.close()
            conn.close()

    def get_schema_version(self) -> int:
        """Get current schema version from database.

        Returns:
            Schema version number, or 0 if not initialized
        """
        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("""
                SELECT value FROM schema_metadata WHERE key = 'schema_version'
            """)
            result = cursor.fetchone()
            return int(result['value']) if result else 0
        except Exception:
            return 0
        finally:
            cursor.close()
            conn.close()

    def verify_schema(self) -> Dict[str, bool]:
        """Verify all tables exist.

        Returns:
            Dict mapping table name to existence boolean
        """
        conn = self.get_connection()
        cursor = conn.cursor()

        tables = [
            'schema_metadata',
            'employee_settings',
            'dynamic_rates',
            'ranks',
            'employee_ranks',
            'shifts',
            'active_bonuses',
            'sync_log'
        ]

        result = {}

        try:
            for table in tables:
                cursor.execute("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables
                        WHERE table_schema = 'public'
                        AND table_name = %s
                    )
                """, (table,))
                result[table] = cursor.fetchone()['exists']

            return result
        finally:
            cursor.close()
            conn.close()

    def get_table_stats(self) -> Dict[str, int]:
        """Get row counts for all tables.

        Returns:
            Dict mapping table name to row count
        """
        conn = self.get_connection()
        cursor = conn.cursor()

        tables = [
            'employee_settings',
            'dynamic_rates',
            'ranks',
            'employee_ranks',
            'shifts',
            'active_bonuses',
            'sync_log'
        ]

        result = {}

        try:
            for table in tables:
                cursor.execute(sql.SQL("SELECT COUNT(*) as count FROM {}").format(
                    sql.Identifier(table)
                ))
                result[table] = cursor.fetchone()['count']

            return result
        finally:
            cursor.close()
            conn.close()


def get_db_connection(
    host: str = "localhost",
    port: int = 5432,
    database: str = "alex12060",
    user: str = "lexun",
    password: Optional[str] = None
) -> psycopg2.extensions.connection:
    """Create a PostgreSQL database connection.

    Args:
        host: PostgreSQL host
        port: PostgreSQL port
        database: Database name
        user: Database user
        password: Database password (from env if not provided)

    Returns:
        psycopg2 connection with RealDictCursor
    """
    return psycopg2.connect(
        host=host,
        port=port,
        database=database,
        user=user,
        password=password or os.getenv("POSTGRES_PASSWORD", ""),
        cursor_factory=extras.RealDictCursor
    )


if __name__ == "__main__":
    # Test schema initialization
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    schema = PostgresSchema()

    print("Initializing PostgreSQL schema...")
    schema.init_schema()

    print("\nVerifying schema...")
    verification = schema.verify_schema()
    for table, exists in verification.items():
        status = "✅" if exists else "❌"
        print(f"{status} {table}")

    print("\nTable statistics:")
    stats = schema.get_table_stats()
    for table, count in stats.items():
        print(f"  {table}: {count} rows")

    print(f"\n✅ Schema version: {schema.get_schema_version()}")
