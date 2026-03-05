"""Test 2.3: Batch product lookup in create_shift."""

import pytest
from unittest.mock import MagicMock, patch, call
from decimal import Decimal


class TestBatchProductQueries:
    """2.3 — Products are fetched with IN query instead of per-product loop."""

    def test_create_shift_uses_in_query(self):
        """create_shift uses SELECT ... WHERE name IN (...) for products."""
        # Read the source to verify the pattern
        import inspect
        from services.postgres_service import PostgresService
        source = inspect.getsource(PostgresService.create_shift)

        assert "WHERE name IN" in source, \
            "create_shift should use IN query for product lookup"
        assert "for product_name, amount in products.items():" not in source or \
            "products_to_insert" in source, \
            "Product loop should use batched product_id_map"

    def test_batch_lookup_pattern_in_source(self):
        """Verify product_id_map pattern exists."""
        import inspect
        from services.postgres_service import PostgresService
        source = inspect.getsource(PostgresService.create_shift)

        assert "product_id_map" in source
        assert "tuple(product_names)" in source
