-- Migration: Add 'monthly_reset' to valid_transaction_type CHECK constraint
-- Date: 2026-03-17
-- Description: The original CHECK constraint in 002_create_hush_transactions.sql
--   did not include 'monthly_reset', causing reset_monthly_hush_balances() to fail
--   silently (INSERT violated constraint → rollback → balances never reset).

ALTER TABLE hush_transactions DROP CONSTRAINT IF EXISTS valid_transaction_type;
ALTER TABLE hush_transactions ADD CONSTRAINT valid_transaction_type CHECK (
    transaction_type IN ('rank_bonus', 'withdrawal', 'adjustment', 'manual_credit', 'monthly_reset')
);

-- Verify
SELECT conname FROM pg_constraint WHERE conname = 'valid_transaction_type';
