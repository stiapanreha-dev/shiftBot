"""Test 4.3: Callback query parsing validation."""

import pytest
import ast


class TestCallbackValidation:
    """4.3 — handle_callback_query wraps dispatch in try/except."""

    @pytest.fixture(autouse=True)
    def load_source(self):
        with open('src/handlers/callback_router.py') as f:
            self.source = f.read()
        self.tree = ast.parse(self.source)

    def test_handler_has_try_except(self):
        """handle_callback_query catches ValueError/IndexError."""
        # Find handle_callback_query function
        for node in ast.walk(self.tree):
            if isinstance(node, ast.AsyncFunctionDef) and node.name == 'handle_callback_query':
                body_source = ast.get_source_segment(self.source, node)
                assert 'try:' in body_source
                assert 'ValueError' in body_source or 'IndexError' in body_source
                return
        pytest.fail("handle_callback_query not found")

    def test_dispatch_function_exists(self):
        """_dispatch_callback helper exists."""
        func_names = [
            node.name for node in ast.walk(self.tree)
            if isinstance(node, ast.AsyncFunctionDef)
        ]
        assert '_dispatch_callback' in func_names

    def test_dispatch_is_async(self):
        """_dispatch_callback is async."""
        for node in ast.walk(self.tree):
            if isinstance(node, ast.AsyncFunctionDef) and node.name == '_dispatch_callback':
                return
        pytest.fail("_dispatch_callback should be async")

    def test_handler_is_async(self):
        """handle_callback_query is async."""
        for node in ast.walk(self.tree):
            if isinstance(node, ast.AsyncFunctionDef) and node.name == 'handle_callback_query':
                return
        pytest.fail("handle_callback_query should be async")
