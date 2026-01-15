#!/usr/bin/env python3
"""Recalculate employee commission tiers based on previous month sales.

Tiers:
- Tier A: $100,000 - $300,000 → 4%
- Tier B: $50,000 - $99,999 → 5%
- Tier C: $0 - $49,999 → 6%

Usage:
    python3 recalculate_employee_tiers.py [--dry-run] [--month YYYY-MM]

Author: Claude Code
Date: 2026-01-15
"""

import argparse
import os
import sys
from datetime import datetime, timedelta
from decimal import Decimal


def get_previous_month(reference_date=None):
    """Get previous month's year and month."""
    if reference_date is None:
        reference_date = datetime.now()

    first_of_month = reference_date.replace(day=1)
    last_month = first_of_month - timedelta(days=1)
    return last_month.year, last_month.month


def calculate_tiers(conn, year, month, dry_run=False):
    """Calculate and update employee tiers based on monthly sales."""
    cur = conn.cursor()

    # Get tier definitions
    cur.execute("""
        SELECT id, name, min_amount, max_amount, percentage
        FROM base_commissions
        WHERE is_active = true
        ORDER BY min_amount DESC
    """)
    tiers = cur.fetchall()

    print(f"\n{'='*60}")
    print(f"ПЕРЕСЧЁТ ТИРОВ ЗА {year}-{month:02d}")
    print(f"{'='*60}")
    print(f"\nТиры:")
    for t in tiers:
        print(f"  {t[1]}: ${t[2]:,.0f} - ${t[3]:,.0f} → {t[4]}%")

    # Calculate monthly sales per employee
    start_date = f"{year}-{month:02d}-01"
    if month == 12:
        end_date = f"{year+1}-01-01"
    else:
        end_date = f"{year}-{month+1:02d}-01"

    cur.execute("""
        SELECT
            e.id,
            e.name,
            e.base_commission_id,
            e.sales_commission,
            COALESCE(SUM(s.total_sales), 0) as monthly_sales,
            COUNT(s.id) as shifts_count
        FROM employees e
        LEFT JOIN shifts s ON e.id = s.employee_id
            AND s.date >= %s
            AND s.date < %s
        WHERE e.is_active = true
        GROUP BY e.id, e.name, e.base_commission_id, e.sales_commission
        ORDER BY monthly_sales DESC
    """, (start_date, end_date))

    employees = cur.fetchall()

    print(f"\n{'='*60}")
    print(f"РЕЗУЛЬТАТЫ:")
    print(f"{'='*60}")

    updates = []

    for emp in employees:
        emp_id, name, current_tier_id, current_commission, monthly_sales, shifts = emp

        # Determine new tier
        new_tier_id = None
        new_percentage = None
        tier_name = "Unknown"

        for tier in tiers:
            tier_id, t_name, min_amt, max_amt, pct = tier
            if Decimal(str(monthly_sales)) >= min_amt:
                new_tier_id = tier_id
                new_percentage = pct
                tier_name = t_name
                break

        # Default to lowest tier (Tier C)
        if new_tier_id is None:
            for tier in tiers:
                if tier[1] == 'Tier C':
                    new_tier_id = tier[0]
                    new_percentage = tier[4]
                    tier_name = 'Tier C'
                    break

        # Check if tier or commission changed
        tier_changed = (current_tier_id != new_tier_id)
        commission_changed = (current_commission != new_percentage)
        changed = tier_changed or commission_changed

        if tier_changed and commission_changed:
            status = "→ ИЗМЕНЕНИЕ (tier + commission)"
        elif tier_changed:
            status = "→ ИЗМЕНЕНИЕ (tier)"
        elif commission_changed:
            status = "→ ИЗМЕНЕНИЕ (commission)"
        else:
            status = "✓ без изменений"

        print(f"\n  {name}:")
        print(f"    Продажи: ${monthly_sales:,.2f} ({shifts} смен)")
        print(f"    Текущий: tier_id={current_tier_id}, commission={current_commission}%")
        print(f"    Новый:   {tier_name} (id={new_tier_id}, {new_percentage}%)")
        print(f"    {status}")

        if changed:
            updates.append({
                'id': emp_id,
                'name': name,
                'new_tier_id': new_tier_id,
                'new_percentage': new_percentage,
                'tier_name': tier_name,
                'monthly_sales': monthly_sales
            })

    print(f"\n{'='*60}")
    print(f"ИТОГО: {len(updates)} изменений")
    print(f"{'='*60}")

    if dry_run:
        print("\n[DRY RUN] Изменения НЕ применены")
        return updates

    # Apply updates
    if updates:
        print("\nПрименяю изменения...")
        for upd in updates:
            cur.execute("""
                UPDATE employees
                SET base_commission_id = %s,
                    sales_commission = %s,
                    last_tier_update = CURRENT_DATE,
                    updated_at = NOW()
                WHERE id = %s
            """, (upd['new_tier_id'], upd['new_percentage'], upd['id']))
            print(f"  ✓ {upd['name']} → {upd['tier_name']} ({upd['new_percentage']}%)")

        conn.commit()
        print(f"\n✅ Обновлено {len(updates)} сотрудников")
    else:
        print("\n✅ Изменений не требуется")

    return updates


def main():
    parser = argparse.ArgumentParser(description='Recalculate employee commission tiers')
    parser.add_argument('--dry-run', action='store_true', help='Show changes without applying')
    parser.add_argument('--month', type=str, help='Month to calculate (YYYY-MM), default: previous month')
    args = parser.parse_args()

    # Parse month
    if args.month:
        try:
            year, month = map(int, args.month.split('-'))
        except ValueError:
            print("Error: Invalid month format. Use YYYY-MM")
            return 1
    else:
        year, month = get_previous_month()

    # Connect to database
    import psycopg2

    conn = psycopg2.connect(
        host=os.getenv('DB_HOST', 'localhost'),
        port=int(os.getenv('DB_PORT', 5432)),
        database=os.getenv('DB_NAME', 'alex12060'),
        user=os.getenv('DB_USER', 'alex12060_user'),
        password=os.getenv('DB_PASSWORD', 'alex12060_pass')
    )

    try:
        calculate_tiers(conn, year, month, dry_run=args.dry_run)
    finally:
        conn.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
