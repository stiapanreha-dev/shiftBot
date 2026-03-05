"""Test 4.1: BaseSyncProcessor helper methods."""

import pytest
from datetime import datetime, date
from decimal import Decimal
from services.sync.base_processor import BaseSyncProcessor


class ConcreteProcessor(BaseSyncProcessor):
    """Concrete subclass for testing abstract base."""

    @property
    def worksheet_name(self):
        return 'Test'

    @property
    def table_name(self):
        return 'test'

    def fetch_record(self, record_id):
        return None

    def format_row(self, record):
        return []


@pytest.fixture
def proc():
    return ConcreteProcessor(spreadsheet=None, db_conn=None)


class TestSafeFloat:
    def test_normal_value(self, proc):
        assert proc._safe_float(Decimal('42.5')) == 42.5

    def test_none_returns_default(self, proc):
        assert proc._safe_float(None) == 0

    def test_custom_default(self, proc):
        assert proc._safe_float(None, default=15.0) == 15.0

    def test_zero(self, proc):
        assert proc._safe_float(0) == 0.0

    def test_integer(self, proc):
        assert proc._safe_float(42) == 42.0


class TestSafeStr:
    def test_normal_value(self, proc):
        assert proc._safe_str('hello') == 'hello'

    def test_none_returns_empty(self, proc):
        assert proc._safe_str(None) == ''

    def test_custom_default(self, proc):
        assert proc._safe_str(None, default='N/A') == 'N/A'

    def test_integer_to_str(self, proc):
        assert proc._safe_str(42) == '42'


class TestFormatDt:
    def test_datetime_default_format(self, proc):
        dt = datetime(2025, 3, 15, 10, 30, 45)
        assert proc._format_dt(dt) == '2025-03-15 10:30:45'

    def test_datetime_custom_format(self, proc):
        dt = datetime(2025, 3, 15, 10, 30, 45)
        assert proc._format_dt(dt, '%Y-%m-%d') == '2025-03-15'

    def test_date_object(self, proc):
        d = date(2025, 3, 15)
        assert proc._format_dt(d, '%Y-%m-%d') == '2025-03-15'

    def test_none_returns_empty(self, proc):
        assert proc._format_dt(None) == ''


class TestBoolStr:
    def test_true(self, proc):
        assert proc._bool_str(True) == 'TRUE'

    def test_false(self, proc):
        assert proc._bool_str(False) == 'FALSE'

    def test_none_is_false(self, proc):
        assert proc._bool_str(None) == 'FALSE'

    def test_truthy_value(self, proc):
        assert proc._bool_str(1) == 'TRUE'


class TestProcessorsUseHelpers:
    """Verify all processors use helper methods instead of inline null checks."""

    @pytest.mark.parametrize("processor_module,class_name", [
        ('services.sync.shift_processor', 'ShiftSyncProcessor'),
        ('services.sync.bonus_processor', 'BonusSyncProcessor'),
        ('services.sync.rank_processor', 'RankSyncProcessor'),
        ('services.sync.employee_processor', 'EmployeeSyncProcessor'),
        ('services.sync.fortnight_processor', 'FortnightSyncProcessor'),
        ('services.sync.hush_processor', 'HushTransactionSyncProcessor'),
    ])
    def test_format_row_uses_helpers(self, processor_module, class_name):
        """format_row should use _safe_float/_format_dt/_bool_str helpers."""
        import importlib, inspect
        mod = importlib.import_module(processor_module)
        cls = getattr(mod, class_name)
        source = inspect.getsource(cls.format_row)
        # Should use at least one helper
        helpers_used = any(h in source for h in [
            '_safe_float', '_safe_str', '_format_dt', '_bool_str',
            'self._safe_float', 'self._safe_str', 'self._format_dt', 'self._bool_str',
        ])
        assert helpers_used, f"{class_name}.format_row should use base processor helpers"
