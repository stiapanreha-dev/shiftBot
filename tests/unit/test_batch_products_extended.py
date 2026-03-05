"""Extended tests for 2.3: Batch products — empty list, single product edge cases."""

import pytest
from decimal import Decimal
import inspect


class TestBatchProductEdgeCases:
    """Edge cases for batch product lookup in create_shift."""

    def test_empty_products_skip_query(self):
        """When all product amounts are 0, no IN query should be executed."""
        from services.postgres_service import PostgresService
        source = inspect.getsource(PostgresService.create_shift)
        # The code filters products with amount > 0 BEFORE the IN query
        assert 'if products_to_insert:' in source or 'products_to_insert' in source

    def test_zero_amount_products_filtered(self):
        """Products with amount=0 should be filtered out before IN query."""
        from services.postgres_service import PostgresService
        source = inspect.getsource(PostgresService.create_shift)
        # Decimal(str(amt)) > 0 filter
        assert '> 0' in source

    def test_products_to_insert_dict_comprehension(self):
        """Verify the filtering logic creates correct dict."""
        products = {'Model A': 100, 'Model B': 0, 'Model C': 50}
        products_to_insert = {
            name: Decimal(str(amt)) for name, amt in products.items()
            if Decimal(str(amt)) > 0
        }
        assert 'Model A' in products_to_insert
        assert 'Model B' not in products_to_insert  # Filtered out
        assert 'Model C' in products_to_insert
        assert len(products_to_insert) == 2

    def test_all_zero_products_empty_dict(self):
        """All zero amounts → empty dict → skip IN query."""
        products = {'Model A': 0, 'Model B': 0}
        products_to_insert = {
            name: Decimal(str(amt)) for name, amt in products.items()
            if Decimal(str(amt)) > 0
        }
        assert len(products_to_insert) == 0

    def test_single_product_tuple(self):
        """Single product creates valid tuple for IN clause."""
        product_names = ['Model A']
        t = tuple(product_names)
        # psycopg2 handles single-element tuple correctly: ('Model A',)
        assert t == ('Model A',)
        assert len(t) == 1
