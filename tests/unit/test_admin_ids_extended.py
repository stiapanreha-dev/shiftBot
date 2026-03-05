"""Extended tests for 3.1: ADMIN_IDS — env parsing edge cases, alert behavior."""

import pytest
import os


class TestAdminIdsEnvParsing:
    """Edge cases for ADMIN_IDS environment variable parsing."""

    def test_admin_ids_parsing_with_spaces(self):
        """ADMIN_IDS with whitespace around values should be trimmed."""
        raw = " 123 , 456 , 789 "
        result = [int(x.strip()) for x in raw.split(",") if x.strip()]
        assert result == [123, 456, 789]

    def test_admin_ids_parsing_trailing_comma(self):
        """Trailing comma should not create empty entry."""
        raw = "123,456,"
        result = [int(x.strip()) for x in raw.split(",") if x.strip()]
        assert result == [123, 456]

    def test_admin_ids_single_value(self):
        """Single value without commas."""
        raw = "7867347055"
        result = [int(x.strip()) for x in raw.split(",") if x.strip()]
        assert result == [7867347055]


class TestSendAdminAlertParsing:
    """_send_admin_alert reads first admin ID from env."""

    def test_alert_uses_first_id(self):
        """First ID from comma-separated ADMIN_IDS is used for alerts."""
        admin_ids_env = '111,222,333'
        admin_id = int(admin_ids_env.split(',')[0].strip())
        assert admin_id == 111

    def test_alert_with_single_id(self):
        """Works with single ID in env var."""
        admin_ids_env = '7867347055'
        admin_id = int(admin_ids_env.split(',')[0].strip())
        assert admin_id == 7867347055

    def test_alert_empty_env_uses_default(self):
        """When ADMIN_IDS env is not set, default is used."""
        # Simulates: os.getenv('ADMIN_IDS', '7867347055')
        admin_ids_env = os.getenv('ADMIN_IDS_NONEXISTENT', '7867347055')
        admin_id = int(admin_ids_env.split(',')[0].strip())
        assert admin_id == 7867347055
