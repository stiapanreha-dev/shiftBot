"""Test 4.1: BaseSyncProcessor helper methods."""

import pytest
from datetime import datetime, date
from decimal import Decimal
from unittest.mock import MagicMock
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


class UpsertProcessor(ConcreteProcessor):
    """Processor with a real record for exercising _handle_upsert."""

    def fetch_record(self, record_id):
        return {'id': record_id}

    def format_row(self, record):
        return [record['id'], 'data']


class TestHandleUpsert:
    """INSERT must not use values.append: with an active basic filter it
    writes after the last VISIBLE row, silently overwriting hidden rows
    (lost shifts 752, 837-840 on 2026-07-01..03)."""

    @pytest.fixture
    def proc(self):
        return UpsertProcessor(spreadsheet=None, db_conn=None)

    def test_insert_writes_past_real_end_of_data(self, proc):
        worksheet = MagicMock()
        worksheet.find.return_value = None  # record not in sheet yet
        worksheet.get_all_values.return_value = [['ID'], ['1'], ['2']]

        assert proc._handle_upsert(worksheet, 3) is True

        worksheet.update.assert_called_once_with(
            values=[[3, 'data']], range_name='A4:Z4')

    def test_insert_never_uses_append_row(self, proc):
        worksheet = MagicMock()
        worksheet.find.return_value = None
        worksheet.get_all_values.return_value = [['ID']]

        proc._handle_upsert(worksheet, 1)

        worksheet.append_row.assert_not_called()

    def test_update_writes_existing_row_in_place(self, proc):
        worksheet = MagicMock()
        worksheet.find.return_value = MagicMock(row=5)

        assert proc._handle_upsert(worksheet, 42) is True

        worksheet.update.assert_called_once_with(
            values=[[42, 'data']], range_name='A5:Z5')
        worksheet.get_all_values.assert_not_called()

    def test_missing_record_returns_false(self, proc):
        worksheet = MagicMock()
        base = ConcreteProcessor(spreadsheet=None, db_conn=None)

        assert base._handle_upsert(worksheet, 1) is False

        worksheet.update.assert_not_called()
        worksheet.append_row.assert_not_called()


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
