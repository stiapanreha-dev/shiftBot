#!/usr/bin/env python3
"""
Migration: Откат к ручному вводу комиссии (sales_commission + dynamic_rates)
"""

import os
import sys
from pathlib import Path

import psycopg2
from psycopg2.extras import RealDictCursor

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
load_dotenv(project_root / '.env')


def get_connection():
    return psycopg2.connect(
        host=os.getenv('DB_HOST', 'localhost'),
        port=os.getenv('DB_PORT', '5432'),
        database=os.getenv('DB_NAME', 'alex12060'),
        user=os.getenv('DB_USER', 'alex12060_user'),
        password=os.getenv('DB_PASSWORD', 'alex12060_pass'),
        cursor_factory=RealDictCursor
    )


def run_migration():
    conn = get_connection()
    cursor = conn.cursor()

    try:
        print("=" * 60)
        print("Откат: Возврат к ручному вводу комиссии")
        print("=" * 60)

        # 1. Восстановить sales_commission
        print("\n1. Восстановление sales_commission в employees...")
        cursor.execute("""
            ALTER TABLE employees
            ADD COLUMN IF NOT EXISTS sales_commission DECIMAL(5,2) DEFAULT 7.0
        """)
        cursor.execute("UPDATE employees SET sales_commission = 7.0 WHERE sales_commission IS NULL")
        print("   ✓ Колонка восстановлена, значение = 7%")

        # 2. Восстановить dynamic_rates
        print("\n2. Восстановление таблицы dynamic_rates...")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS dynamic_rates (
                id SERIAL PRIMARY KEY,
                min_amount DECIMAL(10,2) NOT NULL,
                max_amount DECIMAL(10,2) NOT NULL,
                percentage DECIMAL(5,2) NOT NULL,
                is_active BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT now(),
                updated_at TIMESTAMP DEFAULT now()
            )
        """)

        # Проверить есть ли данные
        cursor.execute("SELECT COUNT(*) as cnt FROM dynamic_rates")
        count = cursor.fetchone()['cnt']

        if count == 0:
            cursor.execute("""
                INSERT INTO dynamic_rates (min_amount, max_amount, percentage) VALUES
                (0.00, 399.99, 0.00),
                (399.99, 699.99, 1.00),
                (699.99, 999.99, 2.00),
                (999.99, 999999.00, 3.00)
            """)
            print("   ✓ Таблица создана и заполнена")
        else:
            print(f"   ✓ Таблица уже существует ({count} записей)")

        # Показать dynamic_rates
        cursor.execute("SELECT * FROM dynamic_rates ORDER BY min_amount")
        for row in cursor.fetchall():
            print(f"   • ${row['min_amount']:,.0f} - ${row['max_amount']:,.0f} → +{row['percentage']}%")

        # 3. Восстановить функцию get_dynamic_rate
        print("\n3. Восстановление функции get_dynamic_rate...")
        cursor.execute("""
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
            $$ LANGUAGE plpgsql
        """)
        print("   ✓ Функция восстановлена")

        # 4. Деактивировать base_commissions
        print("\n4. Деактивация base_commissions...")
        cursor.execute("UPDATE base_commissions SET is_active = FALSE")
        print("   ✓ Тиры деактивированы (оставлены для истории)")

        conn.commit()

        print("\n" + "=" * 60)
        print("✅ Откат успешно завершён!")
        print("=" * 60)

        # Показать итог
        print("\nИтоговое состояние сотрудников:")
        cursor.execute("""
            SELECT name, sales_commission FROM employees
            WHERE is_active = TRUE ORDER BY name
        """)
        for emp in cursor.fetchall():
            print(f"   • {emp['name']}: {emp['sales_commission']}%")

    except Exception as e:
        conn.rollback()
        print(f"\n❌ Ошибка: {e}")
        raise

    finally:
        cursor.close()
        conn.close()


if __name__ == '__main__':
    run_migration()
