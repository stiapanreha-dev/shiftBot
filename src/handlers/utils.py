"""Utility functions for handlers - parsing, formatting, building messages."""

import logging
from decimal import Decimal, InvalidOperation
from typing import Dict

from config import Config
from services.singleton import sheets_service
from services.calculators import CommissionCalculator
from src.time_utils import now_et

logger = logging.getLogger(__name__)


def parse_amount(text: str) -> Decimal:
    """Parse amount from text, handling comma and dot.

    Args:
        text: Amount text.

    Returns:
        Decimal value.

    Raises:
        InvalidOperation: If cannot parse.
    """
    text = text.replace(" ", "").replace(",", ".")
    return Decimal(text)


def get_commission_breakdown(
    employee_id: int,
    commission_pct: float,
    shift_id: int = None
) -> str:
    """Calculate commission breakdown (tier base + bonus).

    Uses CommissionCalculator for consistent breakdown formatting.

    Args:
        employee_id: Employee ID.
        commission_pct: Total commission percentage (can be float or string).
        shift_id: Shift ID (optional, for getting applied bonuses).

    Returns:
        Formatted commission breakdown string.
    """
    sheets = sheets_service
    commission_pct = float(commission_pct)

    # Get tier info
    tier_name = CommissionCalculator.DEFAULT_TIER_NAME
    base_commission = float(CommissionCalculator.DEFAULT_BASE_COMMISSION)
    try:
        tier = sheets.get_employee_tier(employee_id)
        if tier:
            tier_name = tier.get('name', tier_name)
            base_commission = float(tier.get('percentage', base_commission))
    except Exception:
        try:
            settings = sheets.get_employee_settings(employee_id)
            base_commission = float(settings.get("Sales commission", base_commission))
            tier_name = "Base"
        except Exception:
            pass

    # Get bonus percentage if shift_id provided
    bonus_pct = 0.0
    if shift_id:
        try:
            applied_bonuses = sheets.get_shift_applied_bonuses(shift_id)
            for bonus in applied_bonuses:
                if bonus.get("Bonus Type") == "percent_next":
                    bonus_pct += float(bonus.get("Value", 0))
        except Exception as e:
            logger.error(f"Failed to get bonus breakdown: {e}")

    # Format breakdown string
    parts = [f"{tier_name}: {base_commission:.1f}%"]
    if bonus_pct > 0:
        parts.append(f"+{bonus_pct:.1f}% bonus")

    breakdown = " ".join(parts)
    return f"{commission_pct:.2f}% ({breakdown})"


def format_shift_totals(shift_data: Dict, employee_id: int, shift_id: int = None) -> str:
    """Format shift totals section with detailed breakdown.

    Args:
        shift_data: Shift data from Google Sheets.
        employee_id: Employee ID.
        shift_id: Shift ID (optional, for getting applied bonuses).

    Returns:
        Formatted totals string.
    """
    total_sales = Decimal(str(shift_data.get("Total sales", 0)))
    net_sales = Decimal(str(shift_data.get("Net sales", 0)))
    commission_pct = float(shift_data.get("%", 0))
    total_hourly = Decimal(str(shift_data.get("Total hourly", shift_data.get("Total per hour", 0))))
    commissions = Decimal(str(shift_data.get("Commissions", 0)))
    total_made = Decimal(str(shift_data.get("Total made", 0)))

    # Get rolling average and bonus counter
    rolling_average = shift_data.get("rolling_average")
    bonus_counter = shift_data.get("bonus_counter", False)

    # Get commission breakdown with bonus info
    commission_breakdown = get_commission_breakdown(employee_id, commission_pct, shift_id)

    lines = [
        "💵 Totals:",
        f"   • Total sales: ${total_sales:.2f}",
        f"   • Net sales: ${net_sales:.2f}",
        f"   • Commission %: {commission_breakdown}",
        f"   • Total hourly: ${total_hourly:.2f}",
        f"   • Commissions: ${commissions:.2f}",
        f"   • Earned: ${total_made:.2f}",
    ]

    # Add rolling average and bonus counter info
    if rolling_average is not None:
        bonus_icon = "✅" if bonus_counter else "❌"
        lines.append(f"   • Rolling Avg: ${rolling_average:.2f} {bonus_icon}")

    return "\n".join(lines)


def format_shift_details(shift_data: Dict, employee_id: int, shift_id: int) -> str:
    """Format full shift details message (for edit confirmations).

    Args:
        shift_data: Shift data from Google Sheets.
        employee_id: Employee ID.
        shift_id: Shift ID.

    Returns:
        Formatted shift details message.
    """
    lines = [
        f"✅ Shift #{shift_id} Updated",
        "",
        f"📋 ID: {shift_id}",
        f"📅 Date: {shift_data.get('Date', 'N/A')}",
        f"👤 Employee: {shift_data.get('EmployeeName', 'N/A')}",
        "",
        "⏰ Time:",
        f"   • Start: {shift_data.get('Clock in', 'N/A')}",
        f"   • End: {shift_data.get('Clock out', 'N/A')}",
        f"   • Worked hours: {shift_data.get('Worked hours/shift', 0)}",
    ]

    # Get products from shift data
    products = {}
    product_names = sheets_service.get_products()

    for product_name in product_names:
        value = shift_data.get(product_name, "")
        if value and value != "0" and value != 0:
            try:
                products[product_name] = float(value)
            except (ValueError, TypeError):
                pass

    if products:
        lines.extend(["", "💰 Sales:"])
        for product, amount in products.items():
            lines.append(f"   • {product}: {amount:.2f}")

    # Add totals section
    lines.append("")
    lines.append(format_shift_totals(shift_data, employee_id, shift_id))

    return "\n".join(lines)


def build_summary(shift_data: Dict, shift_id: int, created_shift: Dict = None) -> str:
    """Build shift summary message.

    Args:
        shift_data: Shift data dictionary.
        shift_id: Shift ID.
        created_shift: Optional created shift data from Google Sheets.

    Returns:
        Formatted summary string.
    """
    lines = [
        "✅ Shift created",
        "",
        f"📋 ID: {shift_id}",
        f"📅 Date: {shift_data['date']}",
        f"👤 Employee: {shift_data['employee_name']}",
        "",
        "⏰ Time:",
        f"   • Start: {shift_data['clock_in']}",
        f"   • End: {shift_data['clock_out']}",
    ]

    # Get detailed data from created shift if available
    if created_shift:
        worked_hours = created_shift.get("Worked hours/shift", 0)
        lines.append(f"   • Worked hours: {worked_hours}")

    lines.extend([
        "",
        "💰 Sales:",
    ])

    # Add products
    for product, amount in shift_data["products"].items():
        lines.append(f"   • {product}: {amount:.2f}")

    # Get totals from created shift if available
    if created_shift:
        total_sales = Decimal(str(created_shift.get("Total sales", 0)))
        net_sales = Decimal(str(created_shift.get("Net sales", 0)))
        total_made = Decimal(str(created_shift.get("Total made", 0)))
        commission_pct = created_shift.get("%", 0)
        total_per_hour = Decimal(str(created_shift.get("Total per hour", 0)))
        commissions = Decimal(str(created_shift.get("Commissions", 0)))

        # Get commission breakdown with bonus info
        employee_id = shift_data.get("employee_id")
        commission_breakdown = get_commission_breakdown(employee_id, commission_pct, shift_id)

        lines.extend([
            "",
            "💵 Totals:",
            f"   • Total sales: ${total_sales:.2f}",
            f"   • Net sales: ${net_sales:.2f}",
            f"   • Commission %: {commission_breakdown}",
            f"   • Total per hour: ${total_per_hour:.2f}",
            f"   • Commissions: ${commissions:.2f}",
            f"   • Earned: ${total_made:.2f}",
        ])

        # Get applied bonuses for this shift
        _add_bonus_info_to_summary(lines, shift_id, shift_data.get("employee_id"))

    else:
        # Fallback to old calculation (shouldn't happen)
        total_sales = sum(Decimal(str(v)) for v in shift_data["products"].values())
        net_sales = total_sales * Decimal(str(1 - Config.COMMISSION_RATE))
        total_made = net_sales * Decimal(str(Config.PAYOUT_RATE))

        lines.extend([
            "",
            "💵 Totals:",
            f"   • Total sales: ${total_sales:.2f}",
            f"   • Net sales: ${net_sales:.2f}",
            f"   • Earned: ${total_made:.2f}",
        ])

    return "\n".join(lines)


def _add_bonus_info_to_summary(lines: list, shift_id: int, employee_id: int) -> None:
    """Add bonus information to summary lines.

    Args:
        lines: List of summary lines to extend
        shift_id: Shift ID
        employee_id: Employee ID
    """
    try:
        sheets = sheets_service
        applied_bonuses = sheets.get_shift_applied_bonuses(shift_id)

        # Filter bonuses that apply to shifts
        shift_bonuses = [
            b for b in applied_bonuses
            if b.get("Bonus Type") in ["percent_next", "percent_all"]
        ]

        if shift_bonuses:
            # Get current rank
            now = now_et()
            year = now.year
            month = now.month
            rank_record = sheets.get_employee_rank(employee_id, year, month)

            if rank_record:
                current_rank = rank_record.get("Current Rank", "Rookie")
            else:
                current_rank = sheets.determine_rank(employee_id, year, month)

            # Get rank emoji
            from services.rank_service import RankService
            rank_service = RankService(sheets)
            rank_emoji = rank_service._get_rank_emoji(current_rank)

            lines.append("")
            lines.append("🎁 Active Bonuses:")

            for bonus in shift_bonuses:
                bonus_type = bonus.get("Bonus Type", "")
                bonus_value = bonus.get("Value", 0)

                if bonus_type == "percent_next":
                    bonus_desc = f"+{int(bonus_value)}% Commission on your next shift"
                elif bonus_type == "percent_all":
                    bonus_desc = f"+{int(bonus_value)}% from sales of ALL other chatters on your model that day(next shift)"
                else:
                    continue

                lines.append(f"   • Your {current_rank} {rank_emoji} bonus: {bonus_desc}")
    except Exception as e:
        logger.error(f"Failed to get applied bonuses for shift summary: {e}")
