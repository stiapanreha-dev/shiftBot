"""PostgreSQL service - drop-in replacement for SheetsService.

This service provides 100% compatibility with SheetsService interface
but uses the existing PostgreSQL database schema.

Schema mapping:
- shifts table (normalized with shift_products)
- employees table (replaces EmployeeSettings)
- dynamic_rates table (min_amount, max_amount, percentage)
- ranks table (min_amount, max_amount)
- active_bonuses table
- products & shift_products (normalized many-to-many)

Version: 4.0.0 — refactored into mixins (services/mixins/)
"""

import logging
from psycopg2 import extras, pool

from config import Config

from services.mixins import (
    ShiftMixin,
    EmployeeMixin,
    ProductMixin,
    RankMixin,
    BonusMixin,
    RollingMixin,
    FortnightMixin,
    HushMixin,
)

logger = logging.getLogger(__name__)


_connection_pool = None


def _get_pool():
    """Get or create the connection pool (lazy singleton)."""
    global _connection_pool
    if _connection_pool is None or _connection_pool.closed:
        db_params = Config.get_db_params()
        _connection_pool = pool.SimpleConnectionPool(
            minconn=1,
            maxconn=20,
            cursor_factory=extras.RealDictCursor,
            **db_params,
        )
        logger.info("Connection pool created (1-20 connections)")
    return _connection_pool


def get_db_connection(**params):
    """Get PostgreSQL connection from pool (or direct if custom params)."""
    if params:
        import psycopg2
        db_params = Config.get_db_params()
        db_params.update(params)
        return psycopg2.connect(
            **db_params,
            cursor_factory=extras.RealDictCursor
        )
    return _get_pool().getconn()


def return_db_connection(conn):
    """Return a connection to the pool."""
    try:
        p = _get_pool()
        p.putconn(conn)
    except Exception:
        try:
            conn.close()
        except Exception:
            pass


class PostgresService(
    ShiftMixin,
    EmployeeMixin,
    ProductMixin,
    RankMixin,
    BonusMixin,
    RollingMixin,
    FortnightMixin,
    HushMixin,
):
    """PostgreSQL service - drop-in replacement for SheetsService.

    All domain methods are provided by mixins. This class holds only
    connection management (__init__, _get_conn, _put_conn).
    """

    def __init__(self, cache_manager=None, **db_params):
        self.db_params = db_params
        self.cache_manager = cache_manager

        try:
            conn = get_db_connection(**self.db_params)
            self._put_conn(conn)
            logger.info("PostgreSQL service initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize PostgreSQL connection: {e}")
            raise

    def _get_conn(self):
        """Get a database connection (from pool if no custom params)."""
        return get_db_connection(**self.db_params)

    def _put_conn(self, conn):
        """Return connection to pool (or close if custom params)."""
        if self.db_params:
            conn.close()
        else:
            return_db_connection(conn)


# For backward compatibility and testing
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    print("Testing PostgresService...")
    service = PostgresService()

    print(f"\nService initialized")
    print(f"Total shifts: {len(service.get_all_shifts())}")

    shift = service.get_shift_by_id(33)
    if shift:
        print(f"\nShift 33: {shift['employee_name']}, Sales: {shift['total_sales']}")

    print("\nAll tests passed!")
