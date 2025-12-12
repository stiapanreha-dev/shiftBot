-- Migration: Deactivate dynamic_rates
-- Version: 006
-- Date: 2025-12-12
-- Description: Deactivate old dynamic_rates system (keep data for rollback)

-- Deactivate all dynamic rates
UPDATE dynamic_rates SET is_active = FALSE;

-- Add comment explaining deactivation
COMMENT ON TABLE dynamic_rates IS 'DEPRECATED: Deactivated as of 2025-12-12. Replaced by base_commissions tier system.';

-- Note: Table is kept for potential rollback. Can be dropped in future migration.
