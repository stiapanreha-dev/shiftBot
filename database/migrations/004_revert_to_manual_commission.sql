-- Migration: Откат к ручному вводу комиссии
-- Date: 2026-01-05
-- Description: Возврат sales_commission и dynamic_rates

-- ============================================================================
-- 1. Восстановить колонку sales_commission в employees
-- ============================================================================

ALTER TABLE employees
ADD COLUMN IF NOT EXISTS sales_commission DECIMAL(5,2) DEFAULT 7.0;

-- Установить значение 7% всем сотрудникам (или можно взять из tier)
UPDATE employees SET sales_commission = 7.0 WHERE sales_commission IS NULL;

-- ============================================================================
-- 2. Восстановить таблицу dynamic_rates
-- ============================================================================

CREATE TABLE IF NOT EXISTS dynamic_rates (
    id SERIAL PRIMARY KEY,
    min_amount DECIMAL(10,2) NOT NULL,
    max_amount DECIMAL(10,2) NOT NULL,
    percentage DECIMAL(5,2) NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT now(),
    updated_at TIMESTAMP DEFAULT now(),
    CONSTRAINT valid_percentage CHECK (percentage >= 0 AND percentage <= 100),
    CONSTRAINT valid_range CHECK (max_amount > min_amount)
);

-- Создать индекс
CREATE INDEX IF NOT EXISTS idx_dynamic_rates_range
ON dynamic_rates (min_amount, max_amount) WHERE is_active = TRUE;

-- Заполнить данными (0-3% по продажам за смену)
INSERT INTO dynamic_rates (min_amount, max_amount, percentage)
SELECT * FROM (VALUES
    (0.00::DECIMAL, 399.99::DECIMAL, 0.00::DECIMAL),
    (399.99::DECIMAL, 699.99::DECIMAL, 1.00::DECIMAL),
    (699.99::DECIMAL, 999.99::DECIMAL, 2.00::DECIMAL),
    (999.99::DECIMAL, 999999.00::DECIMAL, 3.00::DECIMAL)
) AS v(min_amount, max_amount, percentage)
WHERE NOT EXISTS (SELECT 1 FROM dynamic_rates);

-- ============================================================================
-- 3. Восстановить функцию get_dynamic_rate
-- ============================================================================

CREATE OR REPLACE FUNCTION get_dynamic_rate(p_total_sales DECIMAL)
RETURNS DECIMAL AS $$
DECLARE
    v_rate DECIMAL;
BEGIN
    SELECT percentage INTO v_rate
    FROM dynamic_rates
    WHERE p_total_sales >= min_amount
      AND p_total_sales < max_amount
      AND is_active = TRUE
    ORDER BY min_amount DESC
    LIMIT 1;

    RETURN COALESCE(v_rate, 0);
END;
$$ LANGUAGE plpgsql;

-- ============================================================================
-- 4. Деактивировать base_commissions (оставить для истории)
-- ============================================================================

UPDATE base_commissions SET is_active = FALSE;

-- ============================================================================
-- 5. Комментарии
-- ============================================================================

COMMENT ON COLUMN employees.sales_commission IS 'Базовая комиссия сотрудника (ручной ввод)';
