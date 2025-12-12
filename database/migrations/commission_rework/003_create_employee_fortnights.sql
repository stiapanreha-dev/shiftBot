-- Migration: Create employee_fortnights table
-- Version: 003
-- Date: 2025-12-12
-- Description: History of employee payments by fortnight periods

CREATE TABLE IF NOT EXISTS employee_fortnights (
    id SERIAL PRIMARY KEY,
    employee_id BIGINT NOT NULL REFERENCES employees(id),
    year INT NOT NULL,
    month INT NOT NULL CHECK (month BETWEEN 1 AND 12),
    fortnight INT NOT NULL CHECK (fortnight IN (1, 2)),  -- 1 = days 1-15, 2 = days 16-31

    -- Aggregated data for the period
    total_shifts INT DEFAULT 0,
    total_worked_hours DECIMAL(10,2) DEFAULT 0,
    total_sales DECIMAL(12,2) DEFAULT 0,
    total_commissions DECIMAL(10,2) DEFAULT 0,
    total_hourly_pay DECIMAL(10,2) DEFAULT 0,
    total_made DECIMAL(10,2) DEFAULT 0,

    -- Bonus counter calculations
    bonus_counter_true_count INT DEFAULT 0,
    bonus_amount DECIMAL(10,2) DEFAULT 0,

    -- Final salary
    total_salary DECIMAL(10,2) DEFAULT 0,

    -- Payment info
    payment_date DATE,
    is_paid BOOLEAN DEFAULT FALSE,

    -- Sync status
    synced_to_sheets BOOLEAN DEFAULT FALSE,

    -- Timestamps
    created_at TIMESTAMP DEFAULT now(),
    updated_at TIMESTAMP DEFAULT now(),

    -- Unique constraint
    UNIQUE (employee_id, year, month, fortnight)
);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_employee_fortnights_employee
ON employee_fortnights(employee_id);

CREATE INDEX IF NOT EXISTS idx_employee_fortnights_period
ON employee_fortnights(year, month, fortnight);

CREATE INDEX IF NOT EXISTS idx_employee_fortnights_payment
ON employee_fortnights(is_paid, payment_date);

CREATE INDEX IF NOT EXISTS idx_employee_fortnights_sync
ON employee_fortnights(synced_to_sheets) WHERE synced_to_sheets = FALSE;

-- Function to get fortnight number from day of month
CREATE OR REPLACE FUNCTION get_fortnight_number(day_of_month INT)
RETURNS INT AS $$
BEGIN
    RETURN CASE WHEN day_of_month <= 15 THEN 1 ELSE 2 END;
END;
$$ LANGUAGE plpgsql IMMUTABLE;

-- Function to get payment date for fortnight
CREATE OR REPLACE FUNCTION get_fortnight_payment_date(p_year INT, p_month INT, p_fortnight INT)
RETURNS DATE AS $$
BEGIN
    IF p_fortnight = 1 THEN
        -- F1 (days 1-15): payment on 16th of same month
        RETURN make_date(p_year, p_month, 16);
    ELSE
        -- F2 (days 16-31): payment on 1st of next month
        IF p_month = 12 THEN
            RETURN make_date(p_year + 1, 1, 1);
        ELSE
            RETURN make_date(p_year, p_month + 1, 1);
        END IF;
    END IF;
END;
$$ LANGUAGE plpgsql IMMUTABLE;

-- Trigger to update updated_at
CREATE OR REPLACE FUNCTION update_employee_fortnights_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trigger_employee_fortnights_updated ON employee_fortnights;
CREATE TRIGGER trigger_employee_fortnights_updated
BEFORE UPDATE ON employee_fortnights
FOR EACH ROW EXECUTE FUNCTION update_employee_fortnights_timestamp();

-- Trigger to add to sync_queue
CREATE OR REPLACE FUNCTION trigger_sync_employee_fortnights()
RETURNS TRIGGER AS $$
BEGIN
    INSERT INTO sync_queue (table_name, record_id, operation, data, priority)
    VALUES (
        'employee_fortnights',
        COALESCE(NEW.id, OLD.id),
        TG_OP,
        CASE
            WHEN TG_OP = 'DELETE' THEN to_jsonb(OLD)
            ELSE to_jsonb(NEW)
        END,
        2
    );
    RETURN COALESCE(NEW, OLD);
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS sync_employee_fortnights ON employee_fortnights;
CREATE TRIGGER sync_employee_fortnights
AFTER INSERT OR UPDATE OR DELETE ON employee_fortnights
FOR EACH ROW EXECUTE FUNCTION trigger_sync_employee_fortnights();

COMMENT ON TABLE employee_fortnights IS 'History of employee payments by two-week periods';
COMMENT ON FUNCTION get_fortnight_number(INT) IS 'Get fortnight number (1 or 2) from day of month';
COMMENT ON FUNCTION get_fortnight_payment_date(INT, INT, INT) IS 'Get payment date for fortnight period';
