"""Test 1.1: update_shift_field rejects unknown fields."""

import pytest
from unittest.mock import patch, MagicMock


@pytest.fixture
def service():
    with patch('services.postgres_service._get_pool') as mock_pool:
        mock_conn = MagicMock()
        mock_pool.return_value.getconn.return_value = mock_conn
        mock_conn.cursor.return_value.__enter__ = lambda s: s
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        from services.postgres_service import PostgresService
        svc = PostgresService.__new__(PostgresService)
        svc.db_params = {}
        svc.cache_manager = None
        yield svc


class TestUpdateShiftFieldWhitelist:
    """1.1 — SQL injection prevention via field whitelist."""

    VALID_FIELDS = [
        'Clock in', 'Clock out', 'Worked hours/shift', 'Total sales',
        'Net sales', '%', 'CommissionPct', 'Total per hour',
        'total_per_hour', 'Total hourly', 'Commissions', 'Total made',
        'rolling_average', 'bonus_counter',
    ]

    def test_unknown_field_raises_valueerror(self, service):
        """Arbitrary field name must be rejected."""
        with pytest.raises(ValueError, match="Unknown shift field"):
            service.update_shift_field(1, "Robert'; DROP TABLE shifts;--", "42")

    def test_empty_field_raises_valueerror(self, service):
        with pytest.raises(ValueError, match="Unknown shift field"):
            service.update_shift_field(1, "", "42")

    def test_unmapped_pg_column_raises_valueerror(self, service):
        """Even valid-looking PG column names must be in the whitelist."""
        with pytest.raises(ValueError, match="Unknown shift field"):
            service.update_shift_field(1, "employee_id", "999")

    @pytest.mark.parametrize("field", VALID_FIELDS)
    def test_valid_fields_accepted(self, field, service):
        """All whitelisted fields should not raise ValueError."""
        with patch.object(service, '_get_conn') as mock_get:
            mock_conn = MagicMock()
            mock_get.return_value = mock_conn
            mock_cursor = MagicMock()
            mock_conn.cursor.return_value = mock_cursor
            # Should not raise
            service.update_shift_field(1, field, "100")
