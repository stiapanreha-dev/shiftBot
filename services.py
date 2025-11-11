"""Singleton service instances with caching and hybrid sync enabled.

CHANGELOG (v2.1):
    - Updated to use HybridService instead of SheetsService
    - Hybrid service combines SQLite (fast) + Google Sheets (source of truth)
    - Background sync handled by SEPARATE systemd service (sync_worker.py)
    - Reference data reads are now ~10x faster (SQLite vs Sheets API)

Author: Claude Code (PROMPT 3.2/3.3 - Bidirectional Sync + Standalone Worker)
Date: 2025-11-11
"""

import logging
from cache_manager import CacheManager
from hybrid_service import HybridService

logger = logging.getLogger(__name__)

# Initialize cache manager
cache_manager = CacheManager()
logger.info("✓ CacheManager initialized")

# Initialize HybridService with cache + bidirectional sync
# NOTE: auto_sync=False because sync is handled by separate systemd service
# (alex12060-sync-worker.service runs sync_worker.py)
#
# This replaces the old SheetsService with a drop-in replacement that:
# - Reads reference data from SQLite (fast)
# - Initial sync on startup (pulls from Sheets to SQLite)
# - Periodic sync handled by separate sync_worker.py process
sheets_service = HybridService(
    cache_manager=cache_manager,
    db_path="data/reference_data.db",
    sync_interval=300,  # Not used when auto_sync=False
    auto_sync=False     # Sync handled by separate systemd service
)
logger.info("✓ HybridService initialized (sync handled by alex12060-sync-worker service)")

# Export singleton instances
__all__ = ['sheets_service', 'cache_manager']
