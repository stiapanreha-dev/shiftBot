#!/usr/bin/env python3
"""Create 7 shifts for last 7 days for employee 8152358885.

Each shift has random total_sales between $100-$150.
All calculations done through PostgresService (like bot does).
"""

import sys
import os
import random
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from decimal import Decimal
from datetime import datetime, timedelta
from services.postgres_service import PostgresService

def main():
    print("=" * 70)
    print("Creating 7 shifts for employee 8152358885 (last 7 days)")
    print("=" * 70)

    service = PostgresService()
    employee_id = 8152358885
    employee_name = "pimpingken"

    # Get employee settings
    settings = service.get_employee_settings(employee_id)
    tier = service.get_employee_tier(employee_id)

    print(f"\nEmployee: {employee_name}")
    print(f"Hourly wage: ${settings['Hourly wage']}")
    print(f"Tier: {tier['name']} ({tier['percentage']}%)")
    print()

    created_shifts = []

    # Create shifts for last 7 days (-7 to -1)
    for day_offset in range(-7, 0):
        # Random sales between 100-150
        total_sales = random.randint(100, 150)

        # Calculate date
        shift_date = datetime.now() + timedelta(days=day_offset)
        date_str = shift_date.strftime("%Y/%m/%d")

        # Shift data (8 hours: 9am-5pm)
        shift_data = {
            "date": f"{date_str} 09:00:00",
            "employee_id": employee_id,
            "employee_name": employee_name,
            "clock_in": f"{date_str} 09:00:00",
            "clock_out": f"{date_str} 17:00:00",
            "products": {"Chloe": total_sales},
        }

        # Create shift
        shift_id = service.create_shift(shift_data)
        shift = service.get_shift_by_id(shift_id)

        created_shifts.append({
            'id': shift_id,
            'date': shift_date.strftime("%Y-%m-%d"),
            'total_sales': shift['total_sales'],
            'net_sales': shift['net_sales'],
            'commission_pct': shift['commission_pct'],
            'commissions': shift['commissions'],
            'total_hourly': shift['total_hourly'],
            'total_made': shift['total_made'],
            'rolling_average': shift['rolling_average'],
            'bonus_counter': shift['bonus_counter'],
        })

        print(f"Day {day_offset}: ${total_sales} -> Shift #{shift_id}")

    # Summary table
    print("\n" + "=" * 70)
    print("CREATED SHIFTS SUMMARY")
    print("=" * 70)
    print(f"{'ID':<6} {'Date':<12} {'Sales':>8} {'Net':>8} {'Comm%':>6} {'Comm$':>8} {'Hourly':>8} {'Total':>8} {'RollAvg':>10} {'Bonus'}")
    print("-" * 70)

    for s in created_shifts:
        rolling = f"${s['rolling_average']:.2f}" if s['rolling_average'] else "N/A"
        bonus = "✓" if s['bonus_counter'] else "✗"
        print(f"{s['id']:<6} {s['date']:<12} ${s['total_sales']:>6.0f} ${s['net_sales']:>6.0f} {s['commission_pct']:>5.0f}% ${s['commissions']:>6.2f} ${s['total_hourly']:>6.0f} ${s['total_made']:>6.2f} {rolling:>10} {bonus}")

    print("-" * 70)
    print(f"✅ Created {len(created_shifts)} shifts for employee {employee_id}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
