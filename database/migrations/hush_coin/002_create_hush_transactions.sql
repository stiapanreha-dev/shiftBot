-- Migration: Create hush_transactions table
-- Date: 2026-01-18
-- Description: Transaction history for HUSH coins

CREATE TABLE IF NOT EXISTS hush_transactions (
    id SERIAL PRIMARY KEY,
    employee_id BIGINT NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
    amount DECIMAL(12,2) NOT NULL,
    transaction_type VARCHAR(50) NOT NULL,
    description TEXT,
    rank_id INT REFERENCES ranks(id),
    balance_after DECIMAL(12,2) NOT NULL,
    created_at TIMESTAMP DEFAULT now(),
    synced_to_sheets BOOLEAN DEFAULT FALSE,

    CONSTRAINT valid_transaction_type CHECK (
        transaction_type IN ('rank_bonus', 'withdrawal', 'adjustment', 'manual_credit')
    )
);

-- Indexes for efficient querying
CREATE INDEX IF NOT EXISTS idx_hush_tx_employee ON hush_transactions(employee_id);
CREATE INDEX IF NOT EXISTS idx_hush_tx_date ON hush_transactions(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_hush_tx_synced ON hush_transactions(synced_to_sheets) WHERE synced_to_sheets = FALSE;

-- Trigger for sync to Google Sheets
DROP TRIGGER IF EXISTS trigger_sync_hush_transactions ON hush_transactions;
CREATE TRIGGER trigger_sync_hush_transactions
AFTER INSERT OR UPDATE OR DELETE ON hush_transactions
FOR EACH ROW EXECUTE FUNCTION add_to_sync_queue();

-- Verify
SELECT table_name FROM information_schema.tables WHERE table_name = 'hush_transactions';
