"""Test 5.1: bot.py exits with code 1 on config error."""

import pytest
import inspect


class TestExitCode:
    """5.1 — sys.exit(1) on config validation failure."""

    def test_main_uses_sys_exit(self):
        """bot.main() calls sys.exit(1) on config error, not bare return."""
        from bot import main
        source = inspect.getsource(main)
        assert 'sys.exit(1)' in source, "main() should call sys.exit(1) on config error"
        # Should NOT have bare 'return' after config error
        lines = source.split('\n')
        config_error_section = False
        for line in lines:
            if 'Configuration error' in line:
                config_error_section = True
            if config_error_section and line.strip() == 'return':
                pytest.fail("main() should not use bare 'return' after config error")
            if config_error_section and 'sys.exit' in line:
                break

    def test_sys_imported(self):
        """sys is imported in bot.py."""
        import bot
        source = open(bot.__file__).read()
        assert 'import sys' in source
