"""Database connection management.

This module provides centralized connection management for PostgreSQL.
It uses a simple connection-per-request pattern with proper cleanup.
"""

import logging
from contextlib import contextmanager
from typing import Optional, Generator

import psycopg2
from psycopg2 import extras

from config import Config

logger = logging.getLogger(__name__)


def get_connection(**params):
    """Get PostgreSQL connection with RealDictCursor.

    Args:
        **params: Connection parameters (host, database, user, password, port)
                 If not provided, uses Config.get_db_params()

    Returns:
        psycopg2 connection with RealDictCursor factory
    """
    if not params:
        params = Config.get_db_params()

    conn = psycopg2.connect(
        **params,
        cursor_factory=extras.RealDictCursor
    )
    return conn


class ConnectionManager:
    """Manages database connections with context manager support.

    Usage:
        manager = ConnectionManager()

        # Option 1: Use as context manager
        with manager.get_cursor() as cursor:
            cursor.execute("SELECT * FROM shifts")
            rows = cursor.fetchall()

        # Option 2: Manual control
        conn = manager.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("...")
            conn.commit()
        finally:
            cursor.close()
            conn.close()
    """

    def __init__(self, db_params: Optional[dict] = None):
        """Initialize connection manager.

        Args:
            db_params: Database connection parameters. Uses Config if not provided.
        """
        self.db_params = db_params or Config.get_db_params()

    def get_connection(self):
        """Get a new database connection.

        Returns:
            psycopg2 connection
        """
        return get_connection(**self.db_params)

    @contextmanager
    def get_cursor(self, commit: bool = True) -> Generator:
        """Get database cursor with automatic connection management.

        Args:
            commit: Whether to commit on successful completion

        Yields:
            psycopg2 cursor (RealDictCursor)

        Example:
            with manager.get_cursor() as cursor:
                cursor.execute("SELECT * FROM shifts WHERE id = %s", (shift_id,))
                shift = cursor.fetchone()
        """
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            yield cursor
            if commit:
                conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            cursor.close()
            conn.close()

    @contextmanager
    def transaction(self) -> Generator:
        """Get connection for transaction with explicit commit control.

        Use this when you need to execute multiple statements in a transaction.

        Yields:
            Tuple of (connection, cursor)

        Example:
            with manager.transaction() as (conn, cursor):
                cursor.execute("INSERT INTO shifts ...")
                cursor.execute("INSERT INTO shift_products ...")
                conn.commit()  # Explicit commit required
        """
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            yield conn, cursor
        except Exception:
            conn.rollback()
            raise
        finally:
            cursor.close()
            conn.close()
