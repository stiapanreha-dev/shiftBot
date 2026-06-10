"""Test: ShiftSyncProcessor includes all 6 product models (A-F)."""

import inspect

from services.sync.shift_processor import ShiftSyncProcessor


class TestShiftProcessorProducts:
    """Verify ShiftSyncProcessor fetches and formats all product models."""

    def test_last_column_covers_all_models(self):
        """last_column should be 'U' (21 columns) to include ModelF."""
        proc = ShiftSyncProcessor(spreadsheet=None, db_conn=None)
        assert proc.last_column == 'U'

    def test_product_map_covers_known_ids(self):
        """All historical product ids must map to their sheet slots."""
        from services.sync.shift_processor import PRODUCT_ID_TO_SLOT
        assert PRODUCT_ID_TO_SLOT == {
            1: 'a', 2: 'b', 3: 'c', 9: 'd', 11: 'e', 12: 'f',
        }

    def test_slots_match_sheet_columns(self):
        """Every mapped slot must exist among the sheet model columns."""
        from services.sync.shift_processor import (
            PRODUCT_ID_TO_SLOT, SHEET_MODEL_SLOTS,
        )
        assert SHEET_MODEL_SLOTS == 'abcdef'
        assert set(PRODUCT_ID_TO_SLOT.values()) <= set(SHEET_MODEL_SLOTS)

    def test_format_row_places_models_in_order(self):
        """Model amounts must land in columns 15..20 in slot order."""
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
            'model_a': 1.0, 'model_b': 2.0, 'model_c': 3.0,
            'model_d': 4.0, 'model_e': 5.0, 'model_f': 6.0,
        }
        proc = ShiftSyncProcessor(spreadsheet=None, db_conn=None)
        row = proc.format_row(record)
        assert row[15:21] == [1.0, 2.0, 3.0, 4.0, 5.0, 6.0]

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
