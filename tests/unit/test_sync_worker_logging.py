"""Test 5.3: Sync worker error logging includes traceback."""

import pytest
import inspect


class TestSyncWorkerLogging:
    """5.3 — exc_info=True in sync worker per-record error log."""

    def test_perform_sync_uses_exc_info(self):
        """_perform_sync error handler includes exc_info=True."""
        from pg_sync_worker import PostgresSyncWorker
        source = inspect.getsource(PostgresSyncWorker._perform_sync)

        # Find the per-record error handler
        assert 'exc_info=True' in source, \
            "_perform_sync should log errors with exc_info=True for traceback"

    def test_failed_sync_record_log_has_traceback(self):
        """The specific 'Failed to sync record' log line has exc_info."""
        from pg_sync_worker import PostgresSyncWorker
        source = inspect.getsource(PostgresSyncWorker._perform_sync)

        # Find the line that logs per-record failures
        lines = source.split('\n')
        for line in lines:
            if 'Failed to sync record' in line and 'logger.error' in line:
                assert 'exc_info=True' in line, \
                    "'Failed to sync record' log should include exc_info=True"
                return

        pytest.fail("Could not find 'Failed to sync record' log line")
