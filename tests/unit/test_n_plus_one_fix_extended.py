"""Extended tests for 2.1: N+1 fix — NULL products, mixed shifts, edge cases."""

import pytest
from unittest.mock import MagicMock, patch
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


def make_row(shift_id, product_name=None, product_amount=None, **overrides):
    row = {
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
    row.update(overrides)
    return row


class TestShiftWithoutProducts:
    """LEFT JOIN with NULL products — shift should still be returned."""

    def test_shift_no_products_returned(self, service):
        """Shift with no shift_products rows should still appear in results."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        # LEFT JOIN returns shift row with NULL product fields
        mock_cursor.fetchall.return_value = [
            make_row(1, None, None),
        ]

        with patch.object(service, '_get_conn', return_value=mock_conn):
            with patch.object(service, 'get_products', return_value=['Model A']):
                result = service._fetch_shifts_with_products("", ())

        assert len(result) == 1
        assert result[0]['shift_id'] == 1
        assert result[0]['Model A'] == 0  # Default zero

    def test_mixed_shifts_with_and_without_products(self, service):
        """Some shifts have products, some don't — all should be returned."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_cursor.fetchall.return_value = [
            make_row(1, 'Model A', 100),
            make_row(1, 'Model B', 200),
            make_row(2, None, None),  # Shift 2 has no products
            make_row(3, 'Model A', 50),
        ]

        with patch.object(service, '_get_conn', return_value=mock_conn):
            with patch.object(service, 'get_products', return_value=['Model A', 'Model B']):
                result = service._fetch_shifts_with_products("", ())

        assert len(result) == 3
        # Shift 1 has products
        assert result[0]['Model A'] == 100.0
        assert result[0]['Model B'] == 200.0
        # Shift 2 has no products
        assert result[1]['Model A'] == 0
        assert result[1]['Model B'] == 0
        # Shift 3 has one product
        assert result[2]['Model A'] == 50.0

    def test_many_products_per_shift(self, service):
        """Shift with 5 products — all grouped correctly."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        products = ['A', 'B', 'C', 'D', 'E']
        mock_cursor.fetchall.return_value = [
            make_row(1, p, (i + 1) * 100) for i, p in enumerate(products)
        ]

        with patch.object(service, '_get_conn', return_value=mock_conn):
            with patch.object(service, 'get_products', return_value=products):
                result = service._fetch_shifts_with_products("", ())

        assert len(result) == 1
        assert result[0]['A'] == 100.0
        assert result[0]['E'] == 500.0


class TestShiftRowToDictEdgeCases:
    """Edge cases for _shift_row_to_dict."""

    def test_null_worked_hours(self, service):
        row = make_row(1, worked_hours=None)
        with patch.object(service, 'get_products', return_value=[]):
            result = service._shift_row_to_dict(row)
        assert result['total_hours'] == 0

    def test_null_clock_in_and_out(self, service):
        row = make_row(1, clock_in=None, clock_out=None)
        with patch.object(service, 'get_products', return_value=[]):
            result = service._shift_row_to_dict(row)
        assert result['Clock in'] == ''
        assert result['Clock out'] == ''
        assert result['time_in'] == ''
        assert result['time_out'] == ''

    def test_all_aliases_present(self, service):
        """All expected key aliases exist in result dict."""
        row = make_row(1)
        with patch.object(service, 'get_products', return_value=[]):
            result = service._shift_row_to_dict(row)

        # Check all required keys
        required_keys = [
            'ShiftID', 'ID', 'shift_id',
            'Date', 'shift_date',
            'EmployeeId', 'employee_id',
            'EmployeeName', 'employee_name',
            'Clock in', 'time_in',
            'Clock out', 'time_out',
            'Worked hours/shift', 'total_hours',
            'Total sales', 'total_sales',
            'Net sales', 'net_sales',
            '%', 'CommissionPct', 'commission_pct',
            'Total per hour', 'total_per_hour',
            'Total hourly', 'total_hourly',
            'Commissions', 'commissions', 'commission_amount',
            'Total made', 'total_made',
            'rolling_average', 'Rolling Average',
            'bonus_counter', 'Bonus Counter',
        ]
        for key in required_keys:
            assert key in result, f"Missing key: {key}"
