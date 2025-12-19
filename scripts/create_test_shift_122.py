#!/usr/bin/env python3
"""Create test shift for employee 8152358885 similar to shift #139.

This script emulates exactly what the bot does when creating a shift.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from decimal import Decimal
from datetime import datetime
from services.postgres_service import PostgresService

def main():
    print("=" * 60)
    print("Creating test shift for employee 8152358885")
    print("Similar to shift #139 (StepunR, $122)")
    print("=" * 60)

    service = PostgresService()

    # Employee info
    employee_id = 8152358885
    employee_name = "pimpingken"

    # Get employee settings
    settings = service.get_employee_settings(employee_id)
    print(f"\nEmployee settings:")
    print(f"  Name: {settings['employee_name']}")
    print(f"  Hourly wage: ${settings['Hourly wage']}")

    # Get tier
    tier = service.get_employee_tier(employee_id)
    print(f"  Tier: {tier['name']} ({tier['percentage']}%)")

    # Shift data - exactly as bot creates it
    # Format: YYYY/MM/DD HH:MM:SS
    today = datetime.now().strftime("%Y/%m/%d")

    shift_data = {
        "date": f"{today} 01:00:00",
        "employee_id": employee_id,
        "employee_name": employee_name,
        "clock_in": f"{today} 01:00:00",   # 1 AM
        "clock_out": f"{today} 14:00:00",  # 2 PM (13 hours)
        "products": {"Chloe": 122},         # $122 total
    }

    print(f"\nShift data:")
    print(f"  Date: {today}")
    print(f"  Clock in: 01:00 (1 AM)")
    print(f"  Clock out: 14:00 (2 PM)")
    print(f"  Worked hours: 13")
    print(f"  Products: Chloe = $122")

    # Expected calculations
    print(f"\nExpected calculations (per TZ):")
    total_sales = Decimal('122')
    net_sales = total_sales * Decimal('0.8')
    commission_pct = Decimal(str(tier['percentage']))
    commissions = net_sales * commission_pct / Decimal('100')
    worked_hours = Decimal('13')
    hourly_wage = Decimal(str(settings['Hourly wage']))
    total_hourly = worked_hours * hourly_wage
    total_made = commissions + total_hourly

    print(f"  total_sales = $122")
    print(f"  net_sales = 122 × 0.8 = ${net_sales}")
    print(f"  commission_pct = {commission_pct}% (Tier C)")
    print(f"  commissions = {net_sales} × {commission_pct}% = ${commissions:.2f}")
    print(f"  worked_hours = 13")
    print(f"  total_hourly = 13 × ${hourly_wage} = ${total_hourly}")
    print(f"  total_made = {commissions:.2f} + {total_hourly} = ${total_made:.2f}")

    # Create shift
    print(f"\n" + "=" * 60)
    print("Creating shift...")
    shift_id = service.create_shift(shift_data)
    print(f"✅ Shift created with ID: {shift_id}")

    # Verify
    shift = service.get_shift_by_id(shift_id)

    print(f"\n" + "=" * 60)
    print("ACTUAL VALUES FROM DATABASE:")
    print("=" * 60)
    print(f"  shift_id: {shift['shift_id']}")
    print(f"  total_sales: ${shift['total_sales']}")
    print(f"  net_sales: ${shift['net_sales']}")
    print(f"  commission_pct: {shift['commission_pct']}%")
    print(f"  commissions: ${shift['commissions']}")
    print(f"  worked_hours: {shift['total_hours']}h")
    print(f"  total_hourly: ${shift['total_hourly']}")
    print(f"  total_made: ${shift['total_made']}")
    print(f"  rolling_average: ${shift['rolling_average']}")
    print(f"  bonus_counter: {shift['bonus_counter']}")

    # Verify calculations
    print(f"\n" + "=" * 60)
    print("VERIFICATION:")
    print("=" * 60)

    errors = []

    if Decimal(str(shift['total_sales'])) != total_sales:
        errors.append(f"total_sales: expected {total_sales}, got {shift['total_sales']}")

    if Decimal(str(shift['net_sales'])) != net_sales:
        errors.append(f"net_sales: expected {net_sales}, got {shift['net_sales']}")

    if Decimal(str(shift['commission_pct'])) != commission_pct:
        errors.append(f"commission_pct: expected {commission_pct}, got {shift['commission_pct']}")

    if abs(Decimal(str(shift['commissions'])) - commissions) > Decimal('0.01'):
        errors.append(f"commissions: expected {commissions:.2f}, got {shift['commissions']}")

    if Decimal(str(shift['total_hourly'])) != total_hourly:
        errors.append(f"total_hourly: expected {total_hourly}, got {shift['total_hourly']}")

    if abs(Decimal(str(shift['total_made'])) - total_made) > Decimal('0.01'):
        errors.append(f"total_made: expected {total_made:.2f}, got {shift['total_made']}")

    if errors:
        print("❌ ERRORS:")
        for e in errors:
            print(f"   {e}")
        return 1
    else:
        print("✅ All calculations match TZ formulas!")
        return 0


if __name__ == "__main__":
    sys.exit(main())
