"""Test 1.2: RankSyncProcessor deduplication after append."""

import pytest
from unittest.mock import MagicMock, patch, call
from services.sync.rank_processor import RankSyncProcessor


@pytest.fixture
def processor():
    spreadsheet = MagicMock()
    db_conn = MagicMock()
    return RankSyncProcessor(spreadsheet, db_conn)


@pytest.fixture
def mock_record():
    return {
        'id': 10,
        'employee_id': 123,
        'year': 2025,
        'month': 12,
        'current_rank': 'Gold',
        'previous_rank': 'Silver',
        'updated_at': None,
        'notified': True,
    }


class TestRankDeduplication:
    """1.2 — Race condition dedup in RankSyncProcessor._handle_upsert."""

    def test_no_duplicates_no_deletion(self, processor, mock_record):
        """When no duplicates, nothing is deleted."""
        worksheet = MagicMock()
        # Initial lookup: no existing row
        worksheet.get_all_values.side_effect = [
            [['Header', 'Y', 'M']],  # first call: empty (skip header)
            [['Header', 'Y', 'M'], ['123', '2025', '12', 'Gold', 'Silver', '', 'TRUE']],  # after append
        ]

        with patch.object(processor, 'fetch_record', return_value=mock_record):
            result = processor._handle_upsert(worksheet, 10)

        assert result is True
        worksheet.append_row.assert_called_once()
        worksheet.delete_rows.assert_not_called()

    def test_duplicates_are_cleaned(self, processor, mock_record):
        """When duplicates exist after append, extras are deleted."""
        worksheet = MagicMock()
        # Initial lookup: no existing row
        worksheet.get_all_values.side_effect = [
            [['Header', 'Y', 'M']],  # first call: empty
            [
                ['Header', 'Y', 'M'],
                ['123', '2025', '12', 'Gold', 'Silver', '', 'TRUE'],  # row 2
                ['123', '2025', '12', 'Gold', 'Silver', '', 'TRUE'],  # row 3 (dup)
            ],  # after append: two rows for same key
        ]

        with patch.object(processor, 'fetch_record', return_value=mock_record):
            result = processor._handle_upsert(worksheet, 10)

        assert result is True
        # Should delete row 2 (the earlier duplicate), keeping row 3
        worksheet.delete_rows.assert_called_once_with(2)

    def test_existing_row_updates_no_dedup(self, processor, mock_record):
        """When row already exists, update happens — no dedup needed."""
        worksheet = MagicMock()
        worksheet.get_all_values.return_value = [
            ['Header', 'Y', 'M'],
            ['123', '2025', '12', 'Gold', 'Silver', '', 'TRUE'],
        ]

        with patch.object(processor, 'fetch_record', return_value=mock_record):
            result = processor._handle_upsert(worksheet, 10)

        assert result is True
        worksheet.update.assert_called_once()
        worksheet.append_row.assert_not_called()
        worksheet.delete_rows.assert_not_called()
