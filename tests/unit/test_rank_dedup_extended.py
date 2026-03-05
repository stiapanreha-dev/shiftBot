"""Extended tests for 1.2: RankSyncProcessor — 3+ duplicates, edge cases."""

import pytest
from unittest.mock import MagicMock, patch
from services.sync.rank_processor import RankSyncProcessor


@pytest.fixture
def processor():
    return RankSyncProcessor(MagicMock(), MagicMock())


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


class TestThreePlusDuplicates:
    """Verify cleanup when 3+ duplicate rows exist."""

    def test_three_duplicates_keeps_last(self, processor, mock_record):
        """With 3 duplicates, delete first 2, keep the last."""
        worksheet = MagicMock()
        worksheet.get_all_values.side_effect = [
            [['H', 'Y', 'M']],  # initial: no match
            [
                ['H', 'Y', 'M'],
                ['123', '2025', '12', 'Gold', '', '', 'TRUE'],  # row 2
                ['123', '2025', '12', 'Gold', '', '', 'TRUE'],  # row 3
                ['123', '2025', '12', 'Gold', '', '', 'TRUE'],  # row 4
            ],
        ]

        with patch.object(processor, 'fetch_record', return_value=mock_record):
            processor._handle_upsert(worksheet, 10)

        # Should delete rows 2 and 3 (in reverse order to preserve indices)
        assert worksheet.delete_rows.call_count == 2
        calls = [c.args[0] for c in worksheet.delete_rows.call_args_list]
        # Reverse order: delete row 3 first, then row 2
        assert calls == [3, 2]


class TestCompositeKeyEdgeCases:
    """Composite key matching edge cases."""

    def test_same_employee_different_month_no_match(self, processor, mock_record):
        """Same employee_id but different month should not match."""
        worksheet = MagicMock()
        worksheet.get_all_values.return_value = [
            ['H', 'Y', 'M'],
            ['123', '2025', '11', 'Silver', '', '', 'FALSE'],  # month 11, not 12
        ]

        with patch.object(processor, 'fetch_record', return_value=mock_record):
            processor._handle_upsert(worksheet, 10)

        # Should append (not update row 2)
        worksheet.append_row.assert_called_once()

    def test_short_row_skipped(self, processor, mock_record):
        """Rows with fewer than 3 columns are safely skipped."""
        worksheet = MagicMock()
        worksheet.get_all_values.side_effect = [
            [
                ['H', 'Y', 'M'],
                ['123'],  # only 1 column — should not crash
                ['123', '2025'],  # only 2 columns
            ],
            [
                ['H', 'Y', 'M'],
                ['123'],
                ['123', '2025'],
                ['123', '2025', '12', 'Gold', 'Silver', '', 'TRUE'],
            ],
        ]

        with patch.object(processor, 'fetch_record', return_value=mock_record):
            result = processor._handle_upsert(worksheet, 10)

        assert result is True
        worksheet.append_row.assert_called_once()

    def test_fetch_record_returns_none(self, processor):
        """When record not found in DB, return False."""
        worksheet = MagicMock()

        with patch.object(processor, 'fetch_record', return_value=None):
            result = processor._handle_upsert(worksheet, 999)

        assert result is False
        worksheet.update.assert_not_called()
        worksheet.append_row.assert_not_called()
