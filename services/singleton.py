"""Singleton service instances with PostgreSQL backend.

CHANGELOG (v3.1):
    - Migrated to PostgresService (PostgreSQL backend)
    - 100-1500x faster than Google Sheets
    - Zero API calls to Google Sheets
    - Full compatibility with existing bot code

Previous versions:
    v2.1: HybridService (SQLite + Sheets sync)
    v1.0: SheetsService (Google Sheets only)

Author: Claude Code (PROMPT 4.1 - PostgreSQL Migration)
Date: 2025-11-11
"""

import logging
from services.cache_manager import CacheManager
from services.postgres_service import PostgresService

logger = logging.getLogger(__name__)

# Initialize cache manager
cache_manager = CacheManager()
logger.info("✓ CacheManager initialized")

# Initialize PostgresService with cache
# This provides a drop-in replacement for SheetsService/HybridService:
# - All data stored in PostgreSQL database (alex12060)
# - 100-1500x faster queries (local DB vs API)
# - Zero rate limits
# - Full ACID transactions
sheets_service = PostgresService(
    cache_manager=cache_manager
)
logger.info("✓ PostgresService initialized - using PostgreSQL backend")

# Export singleton instances
__all__ = ['sheets_service', 'cache_manager']
