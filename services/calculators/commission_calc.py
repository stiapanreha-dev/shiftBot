"""Commission calculator - single source of truth for commission calculations."""

import logging
from dataclasses import dataclass
from decimal import Decimal
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)


@dataclass
class CommissionResult:
    """Result of commission calculation."""

    commission_pct: Decimal  # Total commission percentage after bonuses
    base_commission: Decimal  # Base tier commission
    bonus_pct: Decimal  # Bonus percentage added
    flat_bonuses: Decimal  # Flat bonus amounts
    commissions: Decimal  # Commission amount ($)
    total_made: Decimal  # Total earnings (hourly + commission + flat)
    applied_bonus_ids: List[int]  # IDs of applied bonuses
    tier_name: str  # Name of commission tier

    def get_breakdown_string(self) -> str:
        """Get formatted breakdown string for display.

        Returns:
            String like '10.00% (Tier B: 8.0% +2.0% bonus)'
        """
        parts = [f"{self.tier_name}: {self.base_commission:.1f}%"]

        if self.bonus_pct > 0:
            parts.append(f"+{self.bonus_pct:.1f}% bonus")

        breakdown = " ".join(parts)
        return f"{self.commission_pct:.2f}% ({breakdown})"


class CommissionCalculator:
    """Single source of truth for commission calculations.

    This class centralizes all commission calculation logic to ensure
    consistent results across shift creation, updates, and display.
    """

    NET_SALES_RATIO = Decimal('0.8')  # Net = 80% of gross
    DEFAULT_BASE_COMMISSION = Decimal('6.0')
    DEFAULT_TIER_NAME = 'Tier C'

    def calculate(
        self,
        total_sales: Decimal,
        worked_hours: Decimal,
        hourly_wage: Decimal,
        tier: Optional[Dict] = None,
        active_bonuses: Optional[List[Dict]] = None,
        apply_bonuses: bool = True
    ) -> CommissionResult:
        """Calculate commission and total earnings.

        Args:
            total_sales: Total sales amount
            worked_hours: Hours worked
            hourly_wage: Hourly wage rate
            tier: Employee's commission tier dict with 'name' and 'percentage'
            active_bonuses: List of active bonus dicts
            apply_bonuses: Whether to apply bonuses (False for recalculations)

        Returns:
            CommissionResult with all calculated values
        """
        # Get base commission from tier
        if tier:
            base_commission = Decimal(str(tier.get('percentage', self.DEFAULT_BASE_COMMISSION)))
            tier_name = tier.get('name', self.DEFAULT_TIER_NAME)
        else:
            base_commission = self.DEFAULT_BASE_COMMISSION
            tier_name = self.DEFAULT_TIER_NAME

        # Start with base commission
        commission_pct = base_commission
        bonus_pct = Decimal('0')
        flat_bonuses = Decimal('0')
        applied_bonus_ids = []

        # Apply active bonuses if requested
        if apply_bonuses and active_bonuses:
            for bonus in active_bonuses:
                bonus_id = bonus.get("ID")
                bonus_type = bonus.get("Bonus Type", "")
                bonus_value = Decimal(str(bonus.get("Value", 0)))

                if bonus_type == "percent_next":
                    commission_pct += bonus_value
                    bonus_pct += bonus_value
                    applied_bonus_ids.append(bonus_id)
                    logger.info(f"Applied percent_next bonus {bonus_id}: +{bonus_value}%")

                elif bonus_type == "double_commission":
                    # Double the current commission percentage
                    old_pct = commission_pct
                    commission_pct *= Decimal("2")
                    bonus_pct += (commission_pct - old_pct)  # Track the increase
                    applied_bonus_ids.append(bonus_id)
                    logger.info(f"Applied double_commission bonus {bonus_id}: commission doubled")

                elif bonus_type in ["flat", "flat_immediate"]:
                    flat_bonuses += bonus_value
                    applied_bonus_ids.append(bonus_id)
                    logger.info(f"Applied flat bonus {bonus_id}: +${bonus_value}")

        # Calculate monetary values
        net_sales = total_sales * self.NET_SALES_RATIO
        commissions = net_sales * (commission_pct / Decimal('100'))
        total_hourly = worked_hours * hourly_wage
        total_made = commissions + total_hourly + flat_bonuses

        return CommissionResult(
            commission_pct=commission_pct,
            base_commission=base_commission,
            bonus_pct=bonus_pct,
            flat_bonuses=flat_bonuses,
            commissions=commissions,
            total_made=total_made,
            applied_bonus_ids=applied_bonus_ids,
            tier_name=tier_name
        )

    def recalculate_from_existing(
        self,
        total_sales: Decimal,
        worked_hours: Decimal,
        hourly_wage: Decimal,
        existing_commission_pct: Decimal,
        existing_flat_bonuses: Decimal = Decimal('0')
    ) -> CommissionResult:
        """Recalculate commission when only total_sales changes.

        This is used when updating total_sales on an existing shift.
        The commission_pct is already stored with bonuses applied,
        so we just recalculate the monetary values.

        Args:
            total_sales: New total sales amount
            worked_hours: Hours worked
            hourly_wage: Hourly wage rate
            existing_commission_pct: Commission percentage already stored
            existing_flat_bonuses: Flat bonuses already applied

        Returns:
            CommissionResult with recalculated monetary values
        """
        net_sales = total_sales * self.NET_SALES_RATIO
        commissions = net_sales * (existing_commission_pct / Decimal('100'))
        total_hourly = worked_hours * hourly_wage
        total_made = commissions + total_hourly + existing_flat_bonuses

        return CommissionResult(
            commission_pct=existing_commission_pct,
            base_commission=existing_commission_pct,  # Unknown, use total
            bonus_pct=Decimal('0'),  # Unknown for existing shifts
            flat_bonuses=existing_flat_bonuses,
            commissions=commissions,
            total_made=total_made,
            applied_bonus_ids=[],  # Already applied
            tier_name='(existing)'  # Unknown for existing shifts
        )

    @staticmethod
    def calculate_net_sales(total_sales: Decimal) -> Decimal:
        """Calculate net sales from total sales.

        Args:
            total_sales: Gross sales amount

        Returns:
            Net sales (80% of gross)
        """
        return total_sales * CommissionCalculator.NET_SALES_RATIO
