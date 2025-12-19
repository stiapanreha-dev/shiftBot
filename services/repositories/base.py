"""Base repository class with common database operations."""

import logging
from typing import Optional, List, Dict, Any
from contextlib import contextmanager

from services.database import ConnectionManager

logger = logging.getLogger(__name__)


class BaseRepository:
    """Base class for all repositories.

    Provides common database operations and connection management.
    All repositories should inherit from this class.
    """

    def __init__(self, connection_manager: Optional[ConnectionManager] = None):
        """Initialize repository.

        Args:
            connection_manager: ConnectionManager instance. Creates new one if not provided.
        """
        self._conn_manager = connection_manager or ConnectionManager()

    @contextmanager
    def _cursor(self, commit: bool = True):
        """Get database cursor with automatic cleanup.

        Args:
            commit: Whether to commit on success

        Yields:
            Database cursor
        """
        with self._conn_manager.get_cursor(commit=commit) as cursor:
            yield cursor

    @contextmanager
    def _transaction(self):
        """Get connection and cursor for multi-statement transactions.

        Use this when you need to execute multiple statements atomically.

        Yields:
            Tuple of (connection, cursor)
        """
        with self._conn_manager.transaction() as (conn, cursor):
            yield conn, cursor

    def _execute_one(self, query: str, params: tuple = None) -> Optional[Dict]:
        """Execute query and return single result.

        Args:
            query: SQL query
            params: Query parameters

        Returns:
            Single row as dict or None
        """
        with self._cursor(commit=False) as cursor:
            cursor.execute(query, params)
            return cursor.fetchone()

    def _execute_many(self, query: str, params: tuple = None) -> List[Dict]:
        """Execute query and return all results.

        Args:
            query: SQL query
            params: Query parameters

        Returns:
            List of rows as dicts
        """
        with self._cursor(commit=False) as cursor:
            cursor.execute(query, params)
            return cursor.fetchall() or []

    def _execute_insert(self, query: str, params: tuple = None) -> Optional[Any]:
        """Execute INSERT query with RETURNING clause.

        Args:
            query: SQL INSERT query (should include RETURNING)
            params: Query parameters

        Returns:
            Returned value (usually ID)
        """
        with self._cursor(commit=True) as cursor:
            cursor.execute(query, params)
            result = cursor.fetchone()
            return result[0] if result else None

    def _execute_update(self, query: str, params: tuple = None) -> int:
        """Execute UPDATE/DELETE query.

        Args:
            query: SQL UPDATE or DELETE query
            params: Query parameters

        Returns:
            Number of affected rows
        """
        with self._cursor(commit=True) as cursor:
            cursor.execute(query, params)
            return cursor.rowcount
