-- Migration: Create base_commissions table
-- Version: 001
-- Date: 2025-12-12
-- Description: New tier-based commission system replacing fixed commission

-- Create base_commissions table
CREATE TABLE IF NOT EXISTS base_commissions (
    id SERIAL PRIMARY KEY,
    name VARCHAR(50) NOT NULL,              -- 'Tier A', 'Tier B', 'Tier C'
    min_amount DECIMAL(12,2) NOT NULL,      -- Minimum total_sales per month
    max_amount DECIMAL(12,2) NOT NULL,      -- Maximum total_sales per month
    percentage DECIMAL(5,2) NOT NULL,       -- Commission percentage
    is_active BOOLEAN DEFAULT TRUE,
    display_order INT DEFAULT 0,
    created_at TIMESTAMP DEFAULT now(),
    updated_at TIMESTAMP DEFAULT now()
);

-- Create index for lookups
CREATE INDEX IF NOT EXISTS idx_base_commissions_active
ON base_commissions(is_active, display_order);

CREATE INDEX IF NOT EXISTS idx_base_commissions_amounts
ON base_commissions(min_amount, max_amount) WHERE is_active = TRUE;

-- Insert initial tier data
INSERT INTO base_commissions (name, min_amount, max_amount, percentage, display_order)
VALUES
    ('Tier A', 100000.00, 300000.00, 4.0, 1),
    ('Tier B', 50000.00, 99999.99, 5.0, 2),
    ('Tier C', 0.00, 49999.99, 6.0, 3)
ON CONFLICT DO NOTHING;

-- Function to get tier by sales amount
CREATE OR REPLACE FUNCTION get_base_commission_tier(sales_amount DECIMAL)
RETURNS TABLE (
    tier_id INT,
    tier_name VARCHAR(50),
    percentage DECIMAL(5,2)
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        bc.id,
        bc.name,
        bc.percentage
    FROM base_commissions bc
    WHERE bc.is_active = TRUE
      AND sales_amount >= bc.min_amount
      AND sales_amount <= bc.max_amount
    ORDER BY bc.display_order
    LIMIT 1;

    -- Default to Tier C if no match
    IF NOT FOUND THEN
        RETURN QUERY
        SELECT
            bc.id,
            bc.name,
            bc.percentage
        FROM base_commissions bc
        WHERE bc.name = 'Tier C' AND bc.is_active = TRUE
        LIMIT 1;
    END IF;
END;
$$ LANGUAGE plpgsql;

COMMENT ON TABLE base_commissions IS 'Commission tiers based on previous month total sales';
COMMENT ON FUNCTION get_base_commission_tier(DECIMAL) IS 'Get commission tier for given sales amount';
