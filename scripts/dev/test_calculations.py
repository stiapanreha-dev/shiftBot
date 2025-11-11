"""Test script for new calculation logic."""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))
import logging
from decimal import Decimal
from datetime import datetime

from sheets_service import SheetsService
from rank_service import RankService
from time_utils import format_dt, now_et

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def test_employee_settings():
    """Test getting employee settings."""
    print("\n" + "="*60)
    print("TEST 1: Employee Settings")
    print("="*60)

    sheets = SheetsService()
    employee_id = 120962578

    settings = sheets.get_employee_settings(employee_id)

    if settings:
        print(f"✅ Employee {employee_id} settings:")
        print(f"   Hourly wage: ${settings['Hourly wage']:.2f}")
        print(f"   Sales commission: {settings['Sales commission']:.2f}%")
    else:
        print(f"❌ No settings found for employee {employee_id}")


def test_dynamic_rates():
    """Test dynamic rate calculation."""
    print("\n" + "="*60)
    print("TEST 2: Dynamic Rates")
    print("="*60)

    sheets = SheetsService()

    # Get all rates
    rates = sheets.get_dynamic_rates()
    print(f"Dynamic rate ranges:")
    for rate in rates:
        print(f"   ${rate['Min Amount']:.2f} - ${rate['Max Amount']:.2f} → {rate['Percentage']:.2f}%")

    # Test calculation
    employee_id = 120962578
    shift_date = format_dt(now_et())

    dynamic_rate = sheets.calculate_dynamic_rate(employee_id, shift_date)
    print(f"\n✅ Dynamic rate for today: {dynamic_rate:.2f}%")


def test_ranks():
    """Test rank system."""
    print("\n" + "="*60)
    print("TEST 3: Rank System")
    print("="*60)

    sheets = SheetsService()

    # Get all ranks
    ranks = sheets.get_ranks()
    print(f"Configured ranks:")
    for rank in ranks:
        print(f"   {rank['Rank Name']} {rank['Emoji']}: ${int(rank['Min Amount']):,} - ${int(rank['Max Amount']):,}")

    # Test rank determination
    employee_id = 120962578
    now = now_et()
    year = now.year
    month = now.month

    rank = sheets.determine_rank(employee_id, year, month)
    print(f"\n✅ Current rank for employee {employee_id}: {rank}")

    # Get rank bonuses
    bonuses = sheets.get_rank_bonuses(rank)
    print(f"   Bonuses: {bonuses}")


def test_rank_service():
    """Test rank service functionality."""
    print("\n" + "="*60)
    print("TEST 4: Rank Service")
    print("="*60)

    sheets = SheetsService()
    rank_service = RankService(sheets)

    # Test ranks info
    ranks_info = rank_service.get_all_ranks_info()
    print("Ranks info:")
    print(ranks_info)


def test_active_bonuses():
    """Test active bonuses."""
    print("\n" + "="*60)
    print("TEST 5: Active Bonuses")
    print("="*60)

    sheets = SheetsService()
    employee_id = 120962578

    bonuses = sheets.get_active_bonuses(employee_id)

    if bonuses:
        print(f"Active bonuses for employee {employee_id}:")
        for bonus in bonuses:
            print(f"   ID {bonus['ID']}: {bonus['Bonus Type']} = {bonus['Value']}")
    else:
        print(f"No active bonuses for employee {employee_id}")


def test_shift_calculation():
    """Test shift calculation logic."""
    print("\n" + "="*60)
    print("TEST 6: Shift Calculation")
    print("="*60)

    print("\nScenario:")
    print("  Clock in: 09:00")
    print("  Clock out: 17:00")
    print("  Worked hours: 8.00")
    print("  Hourly wage: $15.00")
    print("  Base commission: 8.0%")
    print("  Total sales: $500.00")

    worked_hours = Decimal("8.00")
    hourly_wage = Decimal("15.00")
    base_commission = Decimal("8.0")
    total_sales = Decimal("500.00")
    dynamic_rate = Decimal("2.0")  # For $500 sales

    # Calculations
    total_per_hour = worked_hours * hourly_wage
    net_sales = total_sales * Decimal("0.8")
    commission_percent = base_commission + dynamic_rate
    commissions = net_sales * (commission_percent / Decimal("100"))
    total_made = commissions + total_per_hour

    print(f"\nCalculations:")
    print(f"  Total per hour: ${total_per_hour:.2f}")
    print(f"  Net sales: ${net_sales:.2f}")
    print(f"  Commission %: {commission_percent:.2f}%")
    print(f"  Commissions: ${commissions:.2f}")
    print(f"  Total made: ${total_made:.2f}")

    expected_total = Decimal("120.00") + Decimal("40.00")  # 120 hourly + 40 commissions
    print(f"\n✅ Expected total: ~${expected_total:.2f}")
    print(f"✅ Actual total: ${total_made:.2f}")


def main():
    """Run all tests."""
    print("\n" + "="*60)
    print("TESTING NEW RANK SYSTEM")
    print("="*60)

    try:
        test_employee_settings()
        test_dynamic_rates()
        test_ranks()
        test_rank_service()
        test_active_bonuses()
        test_shift_calculation()

        print("\n" + "="*60)
        print("✅ ALL TESTS COMPLETED")
        print("="*60 + "\n")

    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return 1

    return 0


if __name__ == "__main__":
    exit(main())
