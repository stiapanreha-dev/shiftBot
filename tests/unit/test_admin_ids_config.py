"""Test 3.1: ADMIN_IDS centralized in config.py."""

import pytest
import inspect


class TestAdminIdsConfig:
    """3.1 — ADMIN_IDS loaded from env via Config."""

    def test_config_has_admin_ids(self):
        """Config class has ADMIN_IDS attribute."""
        from config import Config
        assert hasattr(Config, 'ADMIN_IDS')
        assert isinstance(Config.ADMIN_IDS, list)
        assert len(Config.ADMIN_IDS) > 0

    def test_default_admin_ids(self):
        """Default ADMIN_IDS match expected values."""
        from config import Config
        expected = [7867347055, 2125295046, 8152358885, 7367062056]
        assert Config.ADMIN_IDS == expected

    def test_admin_ids_are_integers(self):
        """All ADMIN_IDS are integers."""
        from config import Config
        for aid in Config.ADMIN_IDS:
            assert isinstance(aid, int)

    def test_handlers_main_references_config(self):
        """admin.py imports ADMIN_IDS from Config, not hardcoded."""
        with open('src/handlers/admin.py') as f:
            source = f.read()
        # Should reference Config.ADMIN_IDS, not a hardcoded list
        assert 'Config.ADMIN_IDS' in source
        # Should NOT have hardcoded list
        assert 'ADMIN_IDS = [7867347055' not in source

    def test_sync_worker_uses_env_for_admin_id(self):
        """pg_sync_worker reads admin ID from ADMIN_IDS env, not hardcoded."""
        with open('pg_sync_worker.py') as f:
            source = f.read()
        method_start = source.find("def _send_admin_alert")
        method_end = source.find("\n    def ", method_start + 1)
        if method_end == -1:
            method_end = len(source)
        method_body = source[method_start:method_end]
        # Should read from env var
        assert "os.getenv('ADMIN_IDS'" in method_body or "ADMIN_IDS" in method_body
        # Should NOT have a bare hardcoded assignment like `admin_id = 7867347055`
        assert "admin_id = 7867347055" not in method_body
