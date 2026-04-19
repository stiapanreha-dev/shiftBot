"""Test: ShiftSyncProcessor includes all 6 product models (A-F)."""

import inspect

from services.sync.shift_processor import ShiftSyncProcessor


class TestShiftProcessorProducts:
    """Verify ShiftSyncProcessor fetches and formats all product models."""

    def test_last_column_covers_all_models(self):
        """last_column should be 'U' (21 columns) to include ModelF."""
        proc = ShiftSyncProcessor(spreadsheet=None, db_conn=None)
        assert proc.last_column == 'U'

    def test_fetch_query_includes_all_product_ids(self):
        """SQL query should reference product_id 1,2,3,9,11,12."""
        source = inspect.getsource(ShiftSyncProcessor.fetch_record)
        expected_ids = [1, 2, 3, 9, 11, 12]
        for pid in expected_ids:
            assert f'product_id = {pid}' in source, \
                f"fetch_record missing product_id = {pid}"

    def test_fetch_query_aliases(self):
        """SQL query should have aliases model_a through model_f."""
        source = inspect.getsource(ShiftSyncProcessor.fetch_record)
        for alias in ['model_a', 'model_b', 'model_c', 'model_d', 'model_e', 'model_f']:
            assert f'as {alias}' in source, \
                f"fetch_record missing alias '{alias}'"

    def test_format_row_includes_all_models(self):
        """format_row should reference all 6 model keys."""
        source = inspect.getsource(ShiftSyncProcessor.format_row)
        for key in ['model_a', 'model_b', 'model_c', 'model_d', 'model_e', 'model_f']:
            assert key in source, \
                f"format_row missing key '{key}'"

    def test_format_row_returns_21_columns(self):
        """format_row should return exactly 21 values."""
        from datetime import datetime, date
        record = {
            'id': 1, 'date': date(2026, 4, 10),
            'employee_id': 123, 'employee_name': 'Test',
            'clock_in': datetime(2026, 4, 10, 9, 0),
            'clock_out': datetime(2026, 4, 10, 17, 0),
            'worked_hours': 8.0, 'total_sales': 500.0,
            'net_sales': 460.0, 'commission_pct': 8.0,
            'total_hourly': 120.0, 'commissions': 40.0,
            'total_made': 160.0, 'rolling_average': 450.0,
            'bonus_counter': True,
            'model_a': 100, 'model_b': 100, 'model_c': 100,
            'model_d': 100, 'model_e': 50, 'model_f': 50,
        }
        proc = ShiftSyncProcessor(spreadsheet=None, db_conn=None)
        row = proc.format_row(record)
        assert len(row) == 21, f"Expected 21 columns, got {len(row)}"

    def test_format_row_model_f_position(self):
        """ModelF (Logan) should be the last element (index 20)."""
        from datetime import datetime, date
        record = {
            'id': 1, 'date': date(2026, 4, 10),
            'employee_id': 123, 'employee_name': 'Test',
            'clock_in': datetime(2026, 4, 10, 9, 0),
            'clock_out': datetime(2026, 4, 10, 17, 0),
            'worked_hours': 8.0, 'total_sales': 500.0,
            'net_sales': 460.0, 'commission_pct': 8.0,
            'total_hourly': 120.0, 'commissions': 40.0,
            'total_made': 160.0, 'rolling_average': 450.0,
            'bonus_counter': False,
            'model_a': 100, 'model_b': 200, 'model_c': 0,
            'model_d': 0, 'model_e': 0, 'model_f': 75.5,
        }
        proc = ShiftSyncProcessor(spreadsheet=None, db_conn=None)
        row = proc.format_row(record)
        assert row[20] == 75.5, f"ModelF at index 20 should be 75.5, got {row[20]}"
