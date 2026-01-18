-- Migration: Add hush_balance column to employees table
-- Date: 2026-01-18
-- Description: Adds virtual currency balance for HUSH coins (100 HUSH = $1)

-- Add hush_balance column
ALTER TABLE employees ADD COLUMN IF NOT EXISTS hush_balance DECIMAL(12,2) DEFAULT 0;

-- Create index for potential future queries
CREATE INDEX IF NOT EXISTS idx_employees_hush_balance ON employees(hush_balance);

-- Verify
SELECT column_name, data_type, column_default
FROM information_schema.columns
WHERE table_name = 'employees' AND column_name = 'hush_balance';
