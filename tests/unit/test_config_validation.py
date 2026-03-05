"""Test 3.3: Config.validate_sync() checks SPREADSHEET_ID and GOOGLE_SA_JSON."""

import pytest
from unittest.mock import patch
import os


class TestConfigValidateSync:
    """3.3 — validate_sync checks sync-related config."""

    def test_validate_sync_exists(self):
        """Config has validate_sync classmethod."""
        from config import Config
        assert hasattr(Config, 'validate_sync')
        assert callable(Config.validate_sync)

    def test_validate_sync_raises_on_missing_spreadsheet_id(self):
        """Missing SPREADSHEET_ID raises ValueError."""
        from config import Config
        with patch.object(Config, 'SPREADSHEET_ID', ''):
            with patch.object(Config, 'BOT_TOKEN', 'test'):
                with patch.object(Config, 'POSTGRES_DB', 'test'):
                    with patch.object(Config, 'POSTGRES_USER', 'test'):
                        with patch.object(Config, 'PRODUCTS', ['A']):
                            with pytest.raises(ValueError, match="SPREADSHEET_ID"):
                                Config.validate_sync()

    def test_validate_sync_raises_on_missing_sa_json(self):
        """Missing Google SA JSON file raises ValueError."""
        from config import Config
        with patch.object(Config, 'SPREADSHEET_ID', 'test-id'):
            with patch.object(Config, 'GOOGLE_SA_JSON', '/nonexistent/file.json'):
                with patch.object(Config, 'BOT_TOKEN', 'test'):
                    with patch.object(Config, 'POSTGRES_DB', 'test'):
                        with patch.object(Config, 'POSTGRES_USER', 'test'):
                            with patch.object(Config, 'PRODUCTS', ['A']):
                                with pytest.raises(ValueError, match="credentials file not found"):
                                    Config.validate_sync()

    def test_validate_sync_passes_with_valid_config(self, tmp_path):
        """Valid config passes validation."""
        sa_file = tmp_path / "creds.json"
        sa_file.write_text("{}")

        from config import Config
        with patch.object(Config, 'SPREADSHEET_ID', 'test-id'):
            with patch.object(Config, 'GOOGLE_SA_JSON', str(sa_file)):
                with patch.object(Config, 'BOT_TOKEN', 'test'):
                    with patch.object(Config, 'POSTGRES_DB', 'test'):
                        with patch.object(Config, 'POSTGRES_USER', 'test'):
                            with patch.object(Config, 'PRODUCTS', ['A']):
                                Config.validate_sync()  # Should not raise

    def test_validate_sync_calls_validate(self):
        """validate_sync calls base validate first."""
        from config import Config
        with patch.object(Config, 'BOT_TOKEN', ''):
            with pytest.raises(ValueError, match="BOT_TOKEN"):
                Config.validate_sync()
