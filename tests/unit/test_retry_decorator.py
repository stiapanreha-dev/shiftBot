"""Test 1.3: retry_on_quota_error decorator applied to sync."""

import pytest
from unittest.mock import MagicMock, patch, PropertyMock
import time


class MockResponse:
    def __init__(self, status_code):
        self.status_code = status_code

    def json(self):
        return {"error": {"code": self.status_code, "message": "mock error"}}


class TestRetryOnQuotaError:
    """1.3 — retry_on_quota_error decorator is applied and works."""

    def test_decorator_retries_on_429(self):
        """Decorator retries on 429 with exponential backoff."""
        from pg_sync_worker import retry_on_quota_error
        from gspread.exceptions import APIError

        call_count = 0

        @retry_on_quota_error(max_retries=2, base_delay=0.01)
        def flaky_func():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise APIError(MockResponse(429))
            return "success"

        result = flaky_func()
        assert result == "success"
        assert call_count == 3

    def test_decorator_raises_non_429(self):
        """Non-429 errors are re-raised immediately."""
        from pg_sync_worker import retry_on_quota_error
        from gspread.exceptions import APIError

        @retry_on_quota_error(max_retries=3, base_delay=0.01)
        def error_func():
            raise APIError(MockResponse(500))

        with pytest.raises(APIError):
            error_func()

    def test_decorator_exhausts_retries(self):
        """After max retries, 429 error is raised."""
        from pg_sync_worker import retry_on_quota_error
        from gspread.exceptions import APIError

        @retry_on_quota_error(max_retries=1, base_delay=0.01)
        def always_fails():
            raise APIError(MockResponse(429))

        with pytest.raises(APIError):
            always_fails()

    def test_process_with_retry_exists(self):
        """PostgresSyncWorker has _process_with_retry method."""
        from pg_sync_worker import PostgresSyncWorker
        assert hasattr(PostgresSyncWorker, '_process_with_retry')

    def test_process_with_retry_is_decorated(self):
        """_process_with_retry is wrapped by retry_on_quota_error."""
        from pg_sync_worker import PostgresSyncWorker
        # The wrapper function is created by @wraps, check __wrapped__
        method = PostgresSyncWorker._process_with_retry
        assert hasattr(method, '__wrapped__')
