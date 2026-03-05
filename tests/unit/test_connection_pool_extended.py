"""Extended tests for 2.2: Connection pool — error handling, lifecycle."""

import pytest
from unittest.mock import MagicMock, patch, PropertyMock


class TestReturnDbConnectionErrors:
    """Error handling in return_db_connection."""

    def test_return_conn_closes_on_pool_error(self):
        """If pool.putconn fails, connection is closed directly."""
        with patch('services.postgres_service._get_pool') as mock_pool:
            mock_pool.return_value.putconn.side_effect = Exception("pool error")
            mock_conn = MagicMock()

            from services.postgres_service import return_db_connection
            return_db_connection(mock_conn)

            mock_conn.close.assert_called_once()

    def test_return_conn_silent_on_double_failure(self):
        """If both pool.putconn and conn.close fail, no exception raised."""
        with patch('services.postgres_service._get_pool') as mock_pool:
            mock_pool.return_value.putconn.side_effect = Exception("pool error")
            mock_conn = MagicMock()
            mock_conn.close.side_effect = Exception("close error")

            from services.postgres_service import return_db_connection
            # Should NOT raise
            return_db_connection(mock_conn)


class TestPoolLazyInit:
    """Pool is lazily initialized on first use."""

    def test_pool_created_on_first_getconn(self):
        """_get_pool creates pool on first call."""
        import services.postgres_service as mod
        original_pool = mod._connection_pool

        try:
            mod._connection_pool = None
            with patch('services.postgres_service.pool.SimpleConnectionPool') as mock_ctor:
                mock_ctor.return_value = MagicMock()
                mock_ctor.return_value.closed = False
                mod._get_pool()
                mock_ctor.assert_called_once()
        finally:
            mod._connection_pool = original_pool

    def test_pool_reused_on_subsequent_calls(self):
        """Existing pool is reused, not recreated."""
        import services.postgres_service as mod
        original_pool = mod._connection_pool

        try:
            mock_pool = MagicMock()
            mock_pool.closed = False
            mod._connection_pool = mock_pool

            result = mod._get_pool()
            assert result is mock_pool
        finally:
            mod._connection_pool = original_pool


class TestPutConnBehavior:
    """_put_conn dispatches correctly based on db_params."""

    def test_empty_db_params_returns_to_pool(self):
        """Empty db_params → connection goes back to pool."""
        with patch('services.postgres_service.return_db_connection') as mock_return:
            from services.postgres_service import PostgresService
            svc = PostgresService.__new__(PostgresService)
            svc.db_params = {}
            svc.cache_manager = None

            conn = MagicMock()
            svc._put_conn(conn)

            mock_return.assert_called_once_with(conn)
            conn.close.assert_not_called()

    def test_custom_params_closes_connection(self):
        """Custom db_params → connection is closed, not returned to pool."""
        from services.postgres_service import PostgresService
        svc = PostgresService.__new__(PostgresService)
        svc.db_params = {'host': 'custom-host'}
        svc.cache_manager = None

        conn = MagicMock()
        svc._put_conn(conn)

        conn.close.assert_called_once()
