"""Product and dynamic rate methods for PostgresService."""

import logging
import time
from typing import Dict, List
from decimal import Decimal

logger = logging.getLogger(__name__)

_PRODUCTS_CACHE_TTL = 300  # seconds


class ProductMixin:
    """Product queries and dynamic rate calculations."""

    def get_products(self) -> List[str]:
        """Get list of active products from database.

        Cached in the instance: _shift_row_to_dict calls this per shift row,
        which otherwise turns every shift listing into N+1 queries.
        """
        cached = getattr(self, '_products_cache', None)
        if cached and time.time() - cached[1] < _PRODUCTS_CACHE_TTL:
            return list(cached[0])

        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            cursor.execute("""
                SELECT name FROM products
                WHERE is_active = TRUE
                ORDER BY display_order, id
            """)
            names = [row['name'] for row in cursor.fetchall()]
            self._products_cache = (names, time.time())
            return names
        finally:
            cursor.close()
            self._put_conn(conn)

    def get_dynamic_rates(self) -> List[Dict]:
        """Get all dynamic commission rates in SheetsService format."""
        if self.cache_manager:
            cached = self.cache_manager.get('dynamic_rates', 'all')
            if cached:
                return cached

        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            cursor.execute("""
                SELECT * FROM dynamic_rates
                WHERE is_active = TRUE
                ORDER BY min_amount ASC
            """)
            rates = cursor.fetchall()
            result = []
            for rate in rates:
                result.append({
                    'MinSales': float(rate['min_amount']),
                    'min_sales': float(rate['min_amount']),
                    'MaxSales': float(rate['max_amount']),
                    'max_sales': float(rate['max_amount']),
                    'RatePct': float(rate['percentage']),
                    'rate_pct': float(rate['percentage']),
                })

            if self.cache_manager:
                self.cache_manager.set('dynamic_rates', 'all', result, ttl=900)

            return result
        finally:
            cursor.close()
            self._put_conn(conn)

    def calculate_dynamic_rate(
        self,
        employee_id: int,
        shift_date: str,
        current_total_sales: Decimal = Decimal("0")
    ) -> float:
        """Calculate dynamic commission rate based on current shift sales only."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT get_dynamic_rate(%s) as rate", (current_total_sales,))
            result = cursor.fetchone()
            return float(result['rate']) if result else 0.0
        finally:
            cursor.close()
            self._put_conn(conn)
