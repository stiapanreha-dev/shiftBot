"""Test 2.1: N+1 fix — _fetch_shifts_with_products and _shift_row_to_dict."""

import pytest
from unittest.mock import MagicMock, patch, call
from datetime import date, datetime
from decimal import Decimal


@pytest.fixture
def service():
    with patch('services.postgres_service._get_pool') as mock_pool:
        mock_conn = MagicMock()
        mock_pool.return_value.getconn.return_value = mock_conn
        from services.postgres_service import PostgresService
        svc = PostgresService.__new__(PostgresService)
        svc.db_params = {}
        svc.cache_manager = None
        yield svc


def make_shift_row(shift_id=1, product_name=None, product_amount=None):
    """Create a mock shift row as returned by RealDictCursor."""
    return {
        'id': shift_id,
        'date': date(2025, 1, 15),
        'employee_id': 100,
        'employee_name': 'John',
        'clock_in': datetime(2025, 1, 15, 9, 0),
        'clock_out': datetime(2025, 1, 15, 17, 0),
        'worked_hours': Decimal('8.00'),
        'total_sales': Decimal('500.00'),
        'net_sales': Decimal('400.00'),
        'commission_pct': Decimal('8.00'),
        'total_hourly': Decimal('120.00'),
        'commissions': Decimal('40.00'),
        'total_made': Decimal('160.00'),
        'rolling_average': Decimal('450.00'),
        'bonus_counter': True,
        'product_name': product_name,
        'product_amount': Decimal(str(product_amount)) if product_amount else None,
    }


class TestShiftRowToDict:
    """_shift_row_to_dict converts DB row to SheetsService format."""

    def test_basic_conversion(self, service):
        row = make_shift_row()
        with patch.object(service, 'get_products', return_value=['Model A', 'Model B']):
            result = service._shift_row_to_dict(row)

        assert result['ShiftID'] == 1
        assert result['shift_id'] == 1
        assert result['Date'] == '2025-01-15'
        assert result['Clock in'] == '09:00'
        assert result['Clock out'] == '17:00'
        assert result['total_sales'] == 500.0
        assert result['rolling_average'] == 450.0
        assert result['bonus_counter'] is True

    def test_products_filled(self, service):
        row = make_shift_row()
        products = [
            {'name': 'Model A', 'amount': Decimal('200')},
            {'name': 'Model B', 'amount': Decimal('300')},
        ]
        with patch.object(service, 'get_products', return_value=['Model A', 'Model B']):
            result = service._shift_row_to_dict(row, products)

        assert result['Model A'] == 200.0
        assert result['Model B'] == 300.0

    def test_products_default_zero(self, service):
        row = make_shift_row()
        with patch.object(service, 'get_products', return_value=['Model A', 'Model B']):
            result = service._shift_row_to_dict(row, [])

        assert result['Model A'] == 0
        assert result['Model B'] == 0

    def test_null_clock_out(self, service):
        row = make_shift_row()
        row['clock_out'] = None
        with patch.object(service, 'get_products', return_value=[]):
            result = service._shift_row_to_dict(row)

        assert result['Clock out'] == ''
        assert result['time_out'] == ''

    def test_null_rolling_average(self, service):
        row = make_shift_row()
        row['rolling_average'] = None
        with patch.object(service, 'get_products', return_value=[]):
            result = service._shift_row_to_dict(row)

        assert result['rolling_average'] is None


class TestFetchShiftsWithProducts:
    """_fetch_shifts_with_products uses single JOIN query."""

    def test_single_query_no_n_plus_1(self, service):
        """Only ONE SQL query is executed, not N+1."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor

        # Simulate 2 shifts with products
        mock_cursor.fetchall.return_value = [
            make_shift_row(1, 'Model A', 100),
            make_shift_row(1, 'Model B', 200),
            make_shift_row(2, 'Model A', 300),
        ]

        with patch.object(service, '_get_conn', return_value=mock_conn):
            with patch.object(service, 'get_products', return_value=['Model A', 'Model B']):
                result = service._fetch_shifts_with_products("ORDER BY s.id", ())

        # Should execute exactly 1 query
        assert mock_cursor.execute.call_count == 1
        # Should return 2 shifts
        assert len(result) == 2
        assert result[0]['shift_id'] == 1
        assert result[1]['shift_id'] == 2

    def test_empty_result(self, service):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_cursor.fetchall.return_value = []

        with patch.object(service, '_get_conn', return_value=mock_conn):
            result = service._fetch_shifts_with_products("WHERE 1=0", ())

        assert result == []

    def test_get_all_shifts_uses_fetch(self, service):
        """get_all_shifts delegates to _fetch_shifts_with_products."""
        with patch.object(service, '_fetch_shifts_with_products', return_value=[]) as mock:
            service.get_all_shifts()
        mock.assert_called_once()

    def test_get_last_shifts_uses_fetch(self, service):
        """get_last_shifts delegates to _fetch_shifts_with_products."""
        with patch.object(service, '_fetch_shifts_with_products', return_value=[]) as mock:
            service.get_last_shifts(100, limit=5)
        mock.assert_called_once()
        args = mock.call_args[0]
        assert 'employee_id' in args[0].lower() or '%s' in args[0]
