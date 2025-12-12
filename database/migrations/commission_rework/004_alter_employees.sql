-- Migration: Alter employees table
-- Version: 004
-- Date: 2025-12-12
-- Description: Add base_commission_id FK and tier tracking fields

-- Add new columns
ALTER TABLE employees
ADD COLUMN IF NOT EXISTS base_commission_id INT REFERENCES base_commissions(id),
ADD COLUMN IF NOT EXISTS last_tier_update DATE;

-- Create index for tier lookups
CREATE INDEX IF NOT EXISTS idx_employees_tier
ON employees(base_commission_id) WHERE is_active = TRUE;

-- Migrate existing data: assign Tier C (id=3) to all employees without a tier
-- First, get the Tier C id
DO $$
DECLARE
    tier_c_id INT;
BEGIN
    SELECT id INTO tier_c_id FROM base_commissions WHERE name = 'Tier C' LIMIT 1;

    IF tier_c_id IS NOT NULL THEN
        UPDATE employees
        SET base_commission_id = tier_c_id,
            last_tier_update = CURRENT_DATE
        WHERE base_commission_id IS NULL;

        RAISE NOTICE 'Assigned Tier C (id=%) to employees without tier', tier_c_id;
    ELSE
        RAISE WARNING 'Tier C not found in base_commissions table';
    END IF;
END $$;

-- Note: Keep sales_commission field for backward compatibility
-- It can be removed in a future migration after full transition

COMMENT ON COLUMN employees.base_commission_id IS 'FK to base_commissions tier';
COMMENT ON COLUMN employees.last_tier_update IS 'Date when tier was last recalculated';
