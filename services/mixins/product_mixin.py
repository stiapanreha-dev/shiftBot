"""Product and dynamic rate methods for PostgresService."""

import logging
from typing import Dict, List
from decimal import Decimal

logger = logging.getLogger(__name__)


class ProductMixin:
    """Product queries and dynamic rate calculations."""

    def get_products(self) -> List[str]:
        """Get list of active products from database."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            cursor.execute("""
                SELECT name FROM products
                WHERE is_active = TRUE
                ORDER BY display_order, id
            """)
            return [row['name'] for row in cursor.fetchall()]
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
