"""Tests for monthly HUSH balance reset fix.

Verifies:
1. has_monthly_reset_occurred() exists and queries correctly
2. _check_monthly_hush_reset() no longer requires day==1
3. _check_monthly_hush_reset() uses DB check via has_monthly_reset_occurred
4. Migration file includes 'monthly_reset' in CHECK constraint
"""

import inspect
import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime


class TestHasMonthlyResetOccurred:
    """Tests for HushMixin.has_monthly_reset_occurred()."""

    def test_method_exists(self):
        from services.mixins.hush_mixin import HushMixin
        assert hasattr(HushMixin, 'has_monthly_reset_occurred'), \
            "HushMixin must have has_monthly_reset_occurred method"

    def test_method_signature(self):
        from services.mixins.hush_mixin import HushMixin
        sig = inspect.signature(HushMixin.has_monthly_reset_occurred)
        params = list(sig.parameters.keys())
        assert 'year' in params, "Method must accept 'year' parameter"
        assert 'month' in params, "Method must accept 'month' parameter"

    def test_returns_bool(self):
        from services.mixins.hush_mixin import HushMixin
        hints = HushMixin.has_monthly_reset_occurred.__annotations__
        assert hints.get('return') is bool, "Method must return bool"

    def test_queries_monthly_reset_type(self):
        from services.mixins.hush_mixin import HushMixin
        source = inspect.getsource(HushMixin.has_monthly_reset_occurred)
        assert "monthly_reset" in source, \
            "Must query for 'monthly_reset' transaction type"
        assert "hush_transactions" in source, \
            "Must query hush_transactions table"


class TestCheckMonthlyHushReset:
    """Tests for sync worker _check_monthly_hush_reset()."""

    def test_no_day_check(self):
        """Must NOT have 'now.day != 1' or 'now.day == 1' guard."""
        from pg_sync_worker import PostgresSyncWorker
        source = inspect.getsource(PostgresSyncWorker._check_monthly_hush_reset)
        assert 'now.day != 1' not in source, \
            "Must not check now.day != 1 — reset should work any day"
        assert 'now.day == 1' not in source, \
            "Must not check now.day == 1 — reset should work any day"

    def test_uses_has_monthly_reset_occurred(self):
        """Must call has_monthly_reset_occurred for DB-based idempotency."""
        from pg_sync_worker import PostgresSyncWorker
        source = inspect.getsource(PostgresSyncWorker._check_monthly_hush_reset)
        assert 'has_monthly_reset_occurred' in source, \
            "Must use has_monthly_reset_occurred() for DB check"

    def test_uses_in_memory_cache(self):
        """Must still use last_hush_reset_month as in-memory cache."""
        from pg_sync_worker import PostgresSyncWorker
        source = inspect.getsource(PostgresSyncWorker._check_monthly_hush_reset)
        assert 'last_hush_reset_month' in source, \
            "Must use last_hush_reset_month for in-memory caching"

    def test_calls_reset_when_not_occurred(self):
        """When has_monthly_reset_occurred returns False, must call reset."""
        from pg_sync_worker import PostgresSyncWorker
        source = inspect.getsource(PostgresSyncWorker._check_monthly_hush_reset)
        assert 'reset_monthly_hush_balances' in source, \
            "Must call reset_monthly_hush_balances()"

    def test_skips_when_already_reset_in_db(self):
        """When has_monthly_reset_occurred returns True, must set cache and return."""
        from pg_sync_worker import PostgresSyncWorker
        source = inspect.getsource(PostgresSyncWorker._check_monthly_hush_reset)
        # After DB check returns True, should set cache
        assert 'self.last_hush_reset_month = current_month' in source, \
            "Must cache current_month after DB confirms reset occurred"


class TestMigrationFile:
    """Tests for the migration SQL file."""

    def test_migration_exists(self):
        from pathlib import Path
        migration = Path(__file__).parent.parent.parent / \
            'database/migrations/hush_coin/005_add_monthly_reset_transaction_type.sql'
        assert migration.exists(), \
            "Migration 005_add_monthly_reset_transaction_type.sql must exist"

    def test_migration_adds_monthly_reset(self):
        from pathlib import Path
        migration = Path(__file__).parent.parent.parent / \
            'database/migrations/hush_coin/005_add_monthly_reset_transaction_type.sql'
        content = migration.read_text()
        assert 'monthly_reset' in content, \
            "Migration must add 'monthly_reset' to constraint"
        assert 'valid_transaction_type' in content, \
            "Migration must reference valid_transaction_type constraint"


class TestResetMonthlyHushBalances:
    """Tests for HushMixin.reset_monthly_hush_balances()."""

    def test_uses_monthly_reset_type(self):
        """reset_monthly_hush_balances must insert 'monthly_reset' transactions."""
        from services.mixins.hush_mixin import HushMixin
        source = inspect.getsource(HushMixin.reset_monthly_hush_balances)
        assert "'monthly_reset'" in source, \
            "Must use 'monthly_reset' as transaction_type"
