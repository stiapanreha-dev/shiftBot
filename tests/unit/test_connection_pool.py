"""Test 2.2: Connection pooling."""

import pytest
from unittest.mock import MagicMock, patch


class TestConnectionPool:
    """2.2 — SimpleConnectionPool is used instead of per-call connections."""

    def test_pool_module_imported(self):
        """psycopg2.pool is imported."""
        import services.postgres_service as mod
        from psycopg2 import pool
        # The module should use pool
        assert hasattr(mod, '_get_pool')
        assert hasattr(mod, 'return_db_connection')

    def test_get_db_connection_uses_pool_without_params(self):
        """get_db_connection() without params uses pool."""
        with patch('services.postgres_service._get_pool') as mock_pool:
            mock_conn = MagicMock()
            mock_pool.return_value.getconn.return_value = mock_conn

            from services.postgres_service import get_db_connection
            conn = get_db_connection()

            mock_pool.return_value.getconn.assert_called_once()
            assert conn is mock_conn

    def test_get_db_connection_direct_with_params(self):
        """get_db_connection(**params) creates direct connection."""
        with patch('psycopg2.connect') as mock_connect:
            mock_connect.return_value = MagicMock()

            from services.postgres_service import get_db_connection
            conn = get_db_connection(host='custom-host')

            mock_connect.assert_called_once()

    def test_return_db_connection_puts_back(self):
        """return_db_connection returns conn to pool."""
        with patch('services.postgres_service._get_pool') as mock_pool:
            mock_conn = MagicMock()

            from services.postgres_service import return_db_connection
            return_db_connection(mock_conn)

            mock_pool.return_value.putconn.assert_called_once_with(mock_conn)

    def test_put_conn_with_custom_params_closes(self):
        """_put_conn with custom db_params closes instead of pooling."""
        with patch('services.postgres_service._get_pool') as mock_pool:
            mock_conn = MagicMock()
            mock_pool.return_value.getconn.return_value = mock_conn

            from services.postgres_service import PostgresService
            svc = PostgresService.__new__(PostgresService)
            svc.db_params = {'host': 'custom'}
            svc.cache_manager = None

            svc._put_conn(mock_conn)
            mock_conn.close.assert_called_once()

    def test_put_conn_without_params_uses_pool(self):
        """_put_conn without custom params returns to pool."""
        with patch('services.postgres_service.return_db_connection') as mock_return:
            from services.postgres_service import PostgresService
            svc = PostgresService.__new__(PostgresService)
            svc.db_params = {}
            svc.cache_manager = None

            mock_conn = MagicMock()
            svc._put_conn(mock_conn)

            mock_return.assert_called_once_with(mock_conn)
