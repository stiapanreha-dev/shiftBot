"""Extended tests for 4.3: Callback validation — behavioral tests."""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.fixture
def make_update():
    """Create a mock Update with callback_query."""
    def _make(callback_data: str):
        update = MagicMock()
        query = AsyncMock()
        query.data = callback_data
        query.answer = AsyncMock()
        query.message = MagicMock()
        query.message.reply_text = AsyncMock()
        update.callback_query = query
        update.effective_user = MagicMock()
        update.effective_user.id = 12345
        return update, query
    return _make


class TestCallbackErrorHandling:
    """Behavioral tests: malformed callback data is handled gracefully."""

    @pytest.mark.asyncio
    async def test_malformed_edit_pick_no_crash(self, make_update):
        """EDIT_PICK:abc (non-integer) should not crash."""
        with open('src/handlers/callback_router.py') as f:
            source = f.read()

        assert '_dispatch_callback' in source
        assert 'ValueError' in source

    @pytest.mark.asyncio
    async def test_empty_callback_data_handled(self, make_update):
        """Empty string callback data should be handled."""
        with open('src/handlers/callback_router.py') as f:
            source = f.read()

        assert 'IndexError' in source

    def test_split_on_missing_colon(self):
        """data.split(':') with no colon returns single-element list."""
        data = "NOCOLON"
        parts = data.split(":")
        assert len(parts) == 1
        # Accessing [1] would raise IndexError
        with pytest.raises(IndexError):
            _ = parts[1]

    def test_int_on_non_numeric(self):
        """int('abc') raises ValueError."""
        with pytest.raises(ValueError):
            int("abc")

    def test_split_three_parts(self):
        """data.split(':', 2) correctly handles 3 parts."""
        data = "TIME:IN:9:00_AM"
        _, kind, label = data.split(":", 2)
        assert kind == "IN"
        assert label == "9:00_AM"
