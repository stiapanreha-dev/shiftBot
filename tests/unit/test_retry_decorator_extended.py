"""Extended tests for 1.3: retry_on_quota_error — backoff timing, edge cases."""

import pytest
import time
from unittest.mock import MagicMock


class MockResponse:
    def __init__(self, status_code):
        self.status_code = status_code

    def json(self):
        return {"error": {"code": self.status_code, "message": "mock"}}


class TestRetryBackoffTiming:
    """Verify exponential backoff actually doubles delay."""

    def test_backoff_doubles_each_attempt(self):
        """Delay should be base_delay * 2^attempt."""
        from pg_sync_worker import retry_on_quota_error
        from gspread.exceptions import APIError

        delays = []
        original_sleep = time.sleep

        def mock_sleep(seconds):
            delays.append(seconds)

        call_count = 0

        @retry_on_quota_error(max_retries=3, base_delay=1.0)
        def always_fails():
            nonlocal call_count
            call_count += 1
            raise APIError(MockResponse(429))

        time.sleep = mock_sleep
        try:
            with pytest.raises(APIError):
                always_fails()
        finally:
            time.sleep = original_sleep

        # 3 retries → 3 delays: 1.0, 2.0, 4.0
        assert len(delays) == 3
        assert delays[0] == 1.0
        assert delays[1] == 2.0
        assert delays[2] == 4.0

    def test_max_retries_zero_no_retry(self):
        """max_retries=0 means try once, no retry."""
        from pg_sync_worker import retry_on_quota_error
        from gspread.exceptions import APIError

        call_count = 0

        @retry_on_quota_error(max_retries=0, base_delay=0.01)
        def fails_once():
            nonlocal call_count
            call_count += 1
            raise APIError(MockResponse(429))

        with pytest.raises(APIError):
            fails_once()

        assert call_count == 1

    def test_success_on_first_try_no_delay(self):
        """No delay if first attempt succeeds."""
        from pg_sync_worker import retry_on_quota_error

        delays = []
        original_sleep = time.sleep
        time.sleep = lambda s: delays.append(s)

        @retry_on_quota_error(max_retries=3, base_delay=1.0)
        def succeeds():
            return "ok"

        try:
            result = succeeds()
        finally:
            time.sleep = original_sleep

        assert result == "ok"
        assert len(delays) == 0


class TestRetryWithRealProcessCall:
    """Test _process_with_retry with mock processor."""

    def test_process_with_retry_calls_processor(self):
        """_process_with_retry delegates to processor.process()."""
        from pg_sync_worker import PostgresSyncWorker

        worker = PostgresSyncWorker.__new__(PostgresSyncWorker)
        processor = MagicMock()
        processor.process.return_value = True

        result = worker._process_with_retry(processor, 42, 'INSERT', {'id': 42})

        processor.process.assert_called_once_with(42, 'INSERT', {'id': 42})
        assert result is True
