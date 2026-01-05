#!/usr/bin/env python3
"""
Migration: Применение tier-based комиссий
- Создаёт таблицу base_commissions
- Добавляет base_commission_id в employees
- Мигрирует существующих сотрудников на основе продаж прошлого месяца
- Удаляет dynamic_rates
"""

import os
import sys
from datetime import datetime
from pathlib import Path

import psycopg2
from psycopg2.extras import RealDictCursor

# Добавить корень проекта в path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

# Загрузить .env
from dotenv import load_dotenv
load_dotenv(project_root / '.env')


def get_connection():
    """Получить подключение к PostgreSQL."""
    return psycopg2.connect(
        host=os.getenv('DB_HOST', 'localhost'),
        port=os.getenv('DB_PORT', '5432'),
        database=os.getenv('DB_NAME', 'alex12060'),
        user=os.getenv('DB_USER', 'alex12060_user'),
        password=os.getenv('DB_PASSWORD', 'alex12060_pass'),
        cursor_factory=RealDictCursor
    )


def run_migration():
    """Выполнить миграцию."""
    conn = get_connection()
    cursor = conn.cursor()

    try:
        print("=" * 60)
        print("Миграция: Tier-based комиссии")
        print("=" * 60)

        # 1. Создать таблицу base_commissions
        print("\n1. Создание таблицы base_commissions...")
        cursor.execute("""
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
            )
        """)
        print("   ✓ Таблица создана")

        # 2. Заполнить тиры
        print("\n2. Заполнение тиров...")
        cursor.execute("""
            INSERT INTO base_commissions (name, min_amount, max_amount, percentage, display_order)
            SELECT * FROM (VALUES
                ('Tier A', 100000.00::DECIMAL, 300000.00::DECIMAL, 4.00::DECIMAL, 1),
                ('Tier B', 50000.00::DECIMAL, 99999.99::DECIMAL, 5.00::DECIMAL, 2),
                ('Tier C', 0.00::DECIMAL, 49999.99::DECIMAL, 6.00::DECIMAL, 3)
            ) AS v(name, min_amount, max_amount, percentage, display_order)
            WHERE NOT EXISTS (SELECT 1 FROM base_commissions)
        """)

        cursor.execute("SELECT * FROM base_commissions ORDER BY display_order")
        tiers = cursor.fetchall()
        for tier in tiers:
            print(f"   • {tier['name']}: ${tier['min_amount']:,.0f} - ${tier['max_amount']:,.0f} → {tier['percentage']}%")

        # 3. Добавить колонку base_commission_id в employees
        print("\n3. Добавление base_commission_id в employees...")
        cursor.execute("""
            ALTER TABLE employees
            ADD COLUMN IF NOT EXISTS base_commission_id INT REFERENCES base_commissions(id)
        """)
        print("   ✓ Колонка добавлена")

        # 4. Получить Tier C id
        cursor.execute("SELECT id FROM base_commissions WHERE name = 'Tier C'")
        tier_c = cursor.fetchone()
        tier_c_id = tier_c['id'] if tier_c else 3

        # 5. Мигрировать существующих сотрудников
        print("\n4. Миграция сотрудников...")

        # Получить всех сотрудников
        cursor.execute("SELECT id, name FROM employees WHERE is_active = TRUE")
        employees = cursor.fetchall()

        # Определить прошлый месяц
        now = datetime.now()
        if now.month == 1:
            prev_year = now.year - 1
            prev_month = 12
        else:
            prev_year = now.year
            prev_month = now.month - 1

        print(f"   Анализ продаж за {prev_month:02d}/{prev_year}")

        for emp in employees:
            # Получить total_sales за прошлый месяц
            cursor.execute("""
                SELECT COALESCE(SUM(total_sales), 0) as total
                FROM shifts
                WHERE employee_id = %s
                  AND EXTRACT(YEAR FROM date) = %s
                  AND EXTRACT(MONTH FROM date) = %s
            """, (emp['id'], prev_year, prev_month))

            result = cursor.fetchone()
            total_sales = float(result['total']) if result else 0

            # Определить тир
            cursor.execute("""
                SELECT id, name, percentage FROM base_commissions
                WHERE %s >= min_amount AND %s <= max_amount AND is_active = TRUE
                ORDER BY min_amount DESC LIMIT 1
            """, (total_sales, total_sales))

            tier = cursor.fetchone()
            tier_id = tier['id'] if tier else tier_c_id
            tier_name = tier['name'] if tier else 'Tier C'
            tier_pct = tier['percentage'] if tier else 6.0

            # Обновить сотрудника
            cursor.execute("""
                UPDATE employees
                SET base_commission_id = %s,
                    last_tier_update = CURRENT_DATE,
                    updated_at = now()
                WHERE id = %s
            """, (tier_id, emp['id']))

            print(f"   • {emp['name']}: ${total_sales:,.0f} → {tier_name} ({tier_pct}%)")

        # 6. Создать функции
        print("\n5. Создание функций...")

        cursor.execute("""
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

                IF v_tier_id IS NULL THEN
                    SELECT id INTO v_tier_id FROM base_commissions WHERE name = 'Tier C';
                END IF;

                RETURN v_tier_id;
            END;
            $$ LANGUAGE plpgsql
        """)
        print("   ✓ get_tier_for_sales()")

        cursor.execute("""
            CREATE OR REPLACE FUNCTION get_employee_commission_pct(p_employee_id BIGINT)
            RETURNS DECIMAL AS $$
            DECLARE
                v_percentage DECIMAL;
            BEGIN
                SELECT bc.percentage INTO v_percentage
                FROM employees e
                JOIN base_commissions bc ON e.base_commission_id = bc.id
                WHERE e.id = p_employee_id;

                RETURN COALESCE(v_percentage, 6.00);
            END;
            $$ LANGUAGE plpgsql
        """)
        print("   ✓ get_employee_commission_pct()")

        # 7. Удалить dynamic_rates
        print("\n6. Удаление dynamic_rates...")

        cursor.execute("DROP FUNCTION IF EXISTS get_dynamic_rate(DECIMAL)")
        print("   ✓ Функция get_dynamic_rate удалена")

        cursor.execute("DROP TABLE IF EXISTS dynamic_rates CASCADE")
        print("   ✓ Таблица dynamic_rates удалена")

        # Commit
        conn.commit()

        print("\n" + "=" * 60)
        print("✅ Миграция успешно завершена!")
        print("=" * 60)

        # Показать итоговое состояние
        print("\nИтоговое состояние сотрудников:")
        cursor.execute("""
            SELECT e.name, bc.name as tier, bc.percentage
            FROM employees e
            LEFT JOIN base_commissions bc ON e.base_commission_id = bc.id
            WHERE e.is_active = TRUE
            ORDER BY bc.display_order, e.name
        """)
        for emp in cursor.fetchall():
            print(f"   • {emp['name']}: {emp['tier']} ({emp['percentage']}%)")

    except Exception as e:
        conn.rollback()
        print(f"\n❌ Ошибка миграции: {e}")
        raise

    finally:
        cursor.close()
        conn.close()


if __name__ == '__main__':
    run_migration()
