-- Migration: Переход на tier-based комиссии
-- Date: 2026-01-05
-- Description: Замена dynamic_rates на base_commissions с тирами по месячным продажам

-- ============================================================================
-- 1. Создать таблицу base_commissions
-- ============================================================================

CREATE TABLE IF NOT EXISTS base_commissions (
    id SERIAL PRIMARY KEY,
    name VARCHAR(50) NOT NULL,
    min_amount DECIMAL(12,2) NOT NULL,
    max_amount DECIMAL(12,2) NOT NULL,
    percentage DECIMAL(5,2) NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    display_order INT DEFAULT 0,
    created_at TIMESTAMP DEFAULT now(),
    updated_at TIMESTAMP DEFAULT now(),
    CONSTRAINT valid_commission_range CHECK (max_amount >= min_amount),
    CONSTRAINT valid_commission_percentage CHECK (percentage >= 0 AND percentage <= 100)
);

-- Создать индекс для быстрого поиска тира по сумме
CREATE INDEX IF NOT EXISTS idx_base_commissions_range
ON base_commissions (min_amount, max_amount)
WHERE is_active = TRUE;

-- ============================================================================
-- 2. Заполнить тиры
-- ============================================================================

INSERT INTO base_commissions (name, min_amount, max_amount, percentage, display_order) VALUES
('Tier A', 100000.00, 300000.00, 4.00, 1),
('Tier B', 50000.00, 99999.99, 5.00, 2),
('Tier C', 0.00, 49999.99, 6.00, 3)
ON CONFLICT DO NOTHING;

-- ============================================================================
-- 3. Изменить таблицу employees
-- ============================================================================

-- Добавить колонку base_commission_id
ALTER TABLE employees
ADD COLUMN IF NOT EXISTS base_commission_id INT REFERENCES base_commissions(id);

-- Установить всем сотрудникам Tier C (id=3) по умолчанию
UPDATE employees
SET base_commission_id = (SELECT id FROM base_commissions WHERE name = 'Tier C')
WHERE base_commission_id IS NULL;

-- Удалить старую колонку sales_commission (после проверки!)
-- ALTER TABLE employees DROP COLUMN IF EXISTS sales_commission;

-- ============================================================================
-- 4. Создать функцию определения тира по продажам
-- ============================================================================

CREATE OR REPLACE FUNCTION get_tier_for_sales(p_total_sales DECIMAL)
RETURNS INT AS $$
DECLARE
    v_tier_id INT;
BEGIN
    SELECT id INTO v_tier_id
    FROM base_commissions
    WHERE p_total_sales >= min_amount
      AND p_total_sales <= max_amount
      AND is_active = TRUE
    ORDER BY min_amount DESC
    LIMIT 1;

    -- Если тир не найден, вернуть Tier C
    IF v_tier_id IS NULL THEN
        SELECT id INTO v_tier_id
        FROM base_commissions
        WHERE name = 'Tier C';
    END IF;

    RETURN v_tier_id;
END;
$$ LANGUAGE plpgsql;

-- ============================================================================
-- 5. Создать функцию получения процента комиссии для сотрудника
-- ============================================================================

CREATE OR REPLACE FUNCTION get_employee_commission_pct(p_employee_id BIGINT)
RETURNS DECIMAL AS $$
DECLARE
    v_percentage DECIMAL;
BEGIN
    SELECT bc.percentage INTO v_percentage
    FROM employees e
    JOIN base_commissions bc ON e.base_commission_id = bc.id
    WHERE e.id = p_employee_id;

    -- Если не найдено, вернуть 6% (Tier C)
    RETURN COALESCE(v_percentage, 6.00);
END;
$$ LANGUAGE plpgsql;

-- ============================================================================
-- 6. Создать функцию обновления тира сотрудника
-- ============================================================================

CREATE OR REPLACE FUNCTION update_employee_tier(
    p_employee_id BIGINT,
    p_year INT,
    p_month INT
) RETURNS INT AS $$
DECLARE
    v_total_sales DECIMAL;
    v_new_tier_id INT;
    v_old_tier_id INT;
BEGIN
    -- Получить текущий тир
    SELECT base_commission_id INTO v_old_tier_id
    FROM employees
    WHERE id = p_employee_id;

    -- Получить total_sales за указанный месяц
    SELECT COALESCE(SUM(total_sales), 0) INTO v_total_sales
    FROM shifts
    WHERE employee_id = p_employee_id
      AND EXTRACT(YEAR FROM date) = p_year
      AND EXTRACT(MONTH FROM date) = p_month;

    -- Определить новый тир
    v_new_tier_id := get_tier_for_sales(v_total_sales);

    -- Обновить тир сотрудника
    UPDATE employees
    SET base_commission_id = v_new_tier_id,
        last_tier_update = CURRENT_DATE,
        updated_at = now()
    WHERE id = p_employee_id;

    RETURN v_new_tier_id;
END;
$$ LANGUAGE plpgsql;

-- ============================================================================
-- 7. Удалить dynamic_rates (после проверки!)
-- ============================================================================

-- Сначала удалить функцию, которая использует таблицу
-- DROP FUNCTION IF EXISTS get_dynamic_rate(DECIMAL);

-- Затем удалить таблицу
-- DROP TABLE IF EXISTS dynamic_rates;

-- ============================================================================
-- 8. Комментарии
-- ============================================================================

COMMENT ON TABLE base_commissions IS 'Тиры комиссий по месячным продажам';
COMMENT ON COLUMN base_commissions.name IS 'Название тира (Tier A, B, C)';
COMMENT ON COLUMN base_commissions.min_amount IS 'Минимальная сумма продаж для тира';
COMMENT ON COLUMN base_commissions.max_amount IS 'Максимальная сумма продаж для тира';
COMMENT ON COLUMN base_commissions.percentage IS 'Процент комиссии для тира';
COMMENT ON COLUMN employees.base_commission_id IS 'FK на текущий тир сотрудника';
