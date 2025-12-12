-- Migration: Alter shifts table
-- Version: 005
-- Date: 2025-12-12
-- Description: Rename total_per_hour to total_hourly, add rolling_average and bonus_counter

-- Step 1: Rename total_per_hour to total_hourly
-- Check if column exists before renaming
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'shifts' AND column_name = 'total_per_hour'
    ) THEN
        ALTER TABLE shifts RENAME COLUMN total_per_hour TO total_hourly;
        RAISE NOTICE 'Renamed total_per_hour to total_hourly';
    ELSE
        RAISE NOTICE 'Column total_per_hour does not exist or already renamed';
    END IF;
END $$;

-- Step 2: Add new columns
ALTER TABLE shifts
ADD COLUMN IF NOT EXISTS rolling_average DECIMAL(12,2),
ADD COLUMN IF NOT EXISTS bonus_counter BOOLEAN DEFAULT FALSE;

-- Step 3: Create indexes for efficient queries
CREATE INDEX IF NOT EXISTS idx_shifts_bonus_counter
ON shifts(employee_id, date, bonus_counter);

CREATE INDEX IF NOT EXISTS idx_shifts_rolling_avg
ON shifts(employee_id, date) WHERE rolling_average IS NOT NULL;

-- Step 4: Create function to calculate rolling average
CREATE OR REPLACE FUNCTION calculate_rolling_average(
    p_employee_id BIGINT,
    p_shift_date DATE
)
RETURNS DECIMAL AS $$
DECLARE
    result DECIMAL;
    total_weight INT;
BEGIN
    -- Get weighted average of total_sales for last 7 calendar days
    -- Weights: 1 for oldest, N for newest (where N = number of shifts)
    WITH recent_shifts AS (
        SELECT
            total_sales,
            ROW_NUMBER() OVER (ORDER BY date ASC, clock_in ASC) as weight
        FROM shifts
        WHERE employee_id = p_employee_id
          AND date >= p_shift_date - INTERVAL '7 days'
          AND date < p_shift_date
          AND total_sales IS NOT NULL
        ORDER BY date ASC, clock_in ASC
    )
    SELECT
        CASE
            WHEN COUNT(*) = 0 THEN NULL
            ELSE SUM(total_sales * weight) / SUM(weight)
        END
    INTO result
    FROM recent_shifts;

    RETURN result;
END;
$$ LANGUAGE plpgsql;

-- Step 5: Create function to determine bonus_counter
CREATE OR REPLACE FUNCTION calculate_bonus_counter(
    p_total_sales DECIMAL,
    p_rolling_average DECIMAL
)
RETURNS BOOLEAN AS $$
BEGIN
    -- bonus_counter = true if total_sales >= rolling_average
    -- False if rolling_average is NULL (no history)
    IF p_rolling_average IS NULL THEN
        RETURN FALSE;
    END IF;

    RETURN p_total_sales >= p_rolling_average;
END;
$$ LANGUAGE plpgsql IMMUTABLE;

COMMENT ON COLUMN shifts.rolling_average IS 'Weighted average of total_sales for last 7 days';
COMMENT ON COLUMN shifts.bonus_counter IS 'True if total_sales >= rolling_average';
COMMENT ON FUNCTION calculate_rolling_average(BIGINT, DATE) IS 'Calculate weighted rolling average for employee';
COMMENT ON FUNCTION calculate_bonus_counter(DECIMAL, DECIMAL) IS 'Determine if bonus_counter should be true';
