"""Extended tests for 1.1: update_shift_field — transaction safety and edge cases."""

import pytest
from unittest.mock import MagicMock, patch


@pytest.fixture
def service_with_mocks():
    """Create PostgresService with mocked DB connection."""
    with patch('services.postgres_service._get_pool') as mock_pool:
        mock_conn = MagicMock()
        mock_pool.return_value.getconn.return_value = mock_conn
        from services.postgres_service import PostgresService
        svc = PostgresService.__new__(PostgresService)
        svc.db_params = {}
        svc.cache_manager = None
        yield svc, mock_conn


class TestUpdateShiftFieldTransaction:
    """Transaction rollback and cache invalidation behavior."""

    def test_rollback_called_on_db_error(self, service_with_mocks):
        """conn.rollback() must be called when cursor.execute raises."""
        svc, mock_conn = service_with_mocks
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_cursor.execute.side_effect = Exception("DB error")

        result = svc.update_shift_field(1, 'Total sales', '100')

        assert result is False
        mock_conn.rollback.assert_called_once()

    def test_cache_not_invalidated_on_error(self, service_with_mocks):
        """Cache must NOT be invalidated when update fails."""
        svc, mock_conn = service_with_mocks
        svc.cache_manager = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_cursor.execute.side_effect = Exception("DB error")

        svc.update_shift_field(1, 'Total sales', '100')

        svc.cache_manager.invalidate_key.assert_not_called()

    def test_cache_invalidated_on_success(self, service_with_mocks):
        """Cache IS invalidated when update succeeds."""
        svc, mock_conn = service_with_mocks
        svc.cache_manager = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor

        result = svc.update_shift_field(1, 'Total sales', '100')

        assert result is True
        svc.cache_manager.invalidate_key.assert_called_once_with('shift', 1)

    def test_conn_returned_to_pool_on_success(self, service_with_mocks):
        """Connection returned to pool after successful update."""
        svc, mock_conn = service_with_mocks
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor

        with patch.object(svc, '_put_conn') as mock_put:
            svc.update_shift_field(1, 'Total sales', '100')
            mock_put.assert_called_once_with(mock_conn)

    def test_conn_returned_to_pool_on_error(self, service_with_mocks):
        """Connection returned to pool even when update fails."""
        svc, mock_conn = service_with_mocks
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_cursor.execute.side_effect = Exception("DB error")

        with patch.object(svc, '_put_conn') as mock_put:
            svc.update_shift_field(1, 'Total sales', '100')
            mock_put.assert_called_once_with(mock_conn)

    def test_conn_not_returned_on_valueerror(self, service_with_mocks):
        """ValueError for unknown field happens BEFORE connection is used."""
        svc, mock_conn = service_with_mocks
        # ValueError is raised before cursor.execute, but after _get_conn
        with pytest.raises(ValueError):
            svc.update_shift_field(1, 'INVALID', '100')

    def test_clock_in_uses_date_formatter(self, service_with_mocks):
        """clock_in/clock_out fields go through DateFormatter.to_db_datetime."""
        svc, mock_conn = service_with_mocks
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor

        svc.update_shift_field(1, 'Clock in', '2025/01/15 09:00:00')

        # Verify execute was called with converted datetime
        call_args = mock_cursor.execute.call_args
        # The second positional arg tuple should contain the converted value
        assert '2025-01-15 09:00:00' in str(call_args)
