"""Rank system service for managing employee ranks and bonuses."""

import logging
import random
from typing import Optional, Dict, Tuple
from datetime import datetime

from experimental.sheets_service import SheetsService
from src.time_utils import now_et, format_dt

logger = logging.getLogger(__name__)


class RankService:
    """Service for managing employee ranks and rank changes."""

    def __init__(self, sheets_service: SheetsService):
        """Initialize rank service.

        Args:
            sheets_service: SheetsService instance.
        """
        self.sheets = sheets_service

    def check_and_update_rank(
        self,
        employee_id: int,
        year: int,
        month: int
    ) -> Optional[Dict]:
        """Check if rank changed and update if needed.

        Args:
            employee_id: Telegram user ID.
            year: Year.
            month: Month.

        Returns:
            Dict with rank change info or None if no change:
            {
                "changed": True,
                "old_rank": "Rookie",
                "new_rank": "Hustler",
                "rank_up": True,
                "bonus": "flat_10",
                "emoji": "💪"
            }
        """
        try:
            # Determine new rank based on total sales
            new_rank = self.sheets.determine_rank(employee_id, year, month)

            # Get current rank record
            current_record = self.sheets.get_employee_rank(employee_id, year, month)

            if current_record:
                # Use Previous Rank if available, otherwise fall back to Current Rank
                old_rank = current_record.get("Previous Rank") or current_record.get("Current Rank", "Rookie")
                notified = str(current_record.get("Notified", "false")).lower() == "true"

                # Check if rank changed
                if old_rank != new_rank:
                    # Rank changed
                    is_rank_up = self._is_rank_up(old_rank, new_rank)

                    # Select random bonus for new rank
                    bonus = None
                    if is_rank_up and new_rank != "Rookie":
                        bonus = self._select_random_bonus(new_rank)

                    # Update rank record with new rank and total_sales
                    self.sheets.update_employee_rank(
                        employee_id,
                        new_rank,
                        year,
                        month,
                        format_dt(now_et())
                    )

                    # Get emoji
                    emoji = self._get_rank_emoji(new_rank)

                    logger.info(f"Rank changed for employee {employee_id}: {old_rank} → {new_rank}")

                    return {
                        "changed": True,
                        "old_rank": old_rank,
                        "new_rank": new_rank,
                        "rank_up": is_rank_up,
                        "bonus": bonus,
                        "emoji": emoji
                    }
                else:
                    # Rank unchanged, but update total_sales
                    self.sheets.update_employee_rank(
                        employee_id,
                        new_rank,  # Same rank
                        year,
                        month,
                        format_dt(now_et())
                    )
                    return None
            else:
                # No record yet, create initial rank
                self.sheets.update_employee_rank(
                    employee_id,
                    new_rank,
                    year,
                    month,
                    format_dt(now_et())
                )

                logger.info(f"Initial rank set for employee {employee_id}: {new_rank}")

                # Don't send notification for initial rank (unless it's not Rookie)
                if new_rank != "Rookie":
                    bonus = self._select_random_bonus(new_rank)
                    emoji = self._get_rank_emoji(new_rank)

                    return {
                        "changed": True,
                        "old_rank": "Rookie",
                        "new_rank": new_rank,
                        "rank_up": True,
                        "bonus": bonus,
                        "emoji": emoji
                    }

                return None

        except Exception as e:
            logger.error(f"Failed to check and update rank: {e}")
            return None

    def _is_rank_up(self, old_rank: str, new_rank: str) -> bool:
        """Check if rank change is an upgrade.

        Args:
            old_rank: Old rank name.
            new_rank: New rank name.

        Returns:
            True if rank up, False if rank down.
        """
        rank_order = [
            "Rookie",
            "Hustler",
            "Closer",
            "Shark",
            "King of Greed",
            "Chatting God"
        ]

        try:
            old_idx = rank_order.index(old_rank)
            new_idx = rank_order.index(new_rank)
            return new_idx > old_idx
        except ValueError:
            return False

    def _select_random_bonus(self, rank_name: str) -> Optional[str]:
        """Select random bonus for rank.

        Args:
            rank_name: Rank name.

        Returns:
            Bonus code or None.
        """
        bonuses = self.sheets.get_rank_bonuses(rank_name)

        if bonuses:
            selected = random.choice(bonuses)
            logger.info(f"Selected random bonus for {rank_name}: {selected}")
            return selected

        return None

    def _get_rank_emoji(self, rank_name: str) -> str:
        """Get emoji for rank.

        Args:
            rank_name: Rank name.

        Returns:
            Emoji string.
        """
        ranks = self.sheets.get_ranks()
        for rank in ranks:
            if rank.get("Rank Name") == rank_name:
                return rank.get("Emoji", "")

        return ""

    def apply_rank_bonus(
        self,
        employee_id: int,
        bonus_code: str,
        current_shift_id: Optional[int] = None
    ) -> None:
        """Apply rank bonus (create ActiveBonuses record).

        Args:
            employee_id: Telegram user ID.
            bonus_code: Bonus code (e.g., 'flat_10', 'percent_next_1').
            current_shift_id: ID of current shift (for immediate bonuses).
        """
        try:
            # Parse bonus code
            bonus_type, bonus_value = self._parse_bonus_code(bonus_code)

            if not bonus_type:
                logger.warning(f"Unknown bonus code: {bonus_code}")
                return

            # Create bonus record
            created_at = format_dt(now_et())

            if bonus_type in ["flat_immediate", "percent_prev", "percent_all"]:
                # These bonuses are applied immediately to current shift
                # They should have been applied during shift creation
                logger.info(f"Bonus {bonus_code} should be applied immediately (during shift creation)")
                return

            elif bonus_type in ["percent_next", "double_commission"]:
                # These bonuses apply to next shift
                self.sheets.create_bonus(
                    employee_id,
                    bonus_type,
                    bonus_value,
                    created_at
                )
                logger.info(f"Created {bonus_type} bonus for employee {employee_id}")

            elif bonus_type == "flat":
                # Flat bonus - add to current shift Total made
                if current_shift_id:
                    # Apply immediately by updating Total made
                    self.sheets.create_bonus(
                        employee_id,
                        "flat_immediate",
                        bonus_value,
                        created_at,
                        current_shift_id
                    )
                    # Update shift Total made
                    shift = self.sheets.get_shift_by_id(current_shift_id)
                    if shift:
                        from decimal import Decimal
                        current_total = Decimal(str(shift.get("Total made", 0)))
                        new_total = current_total + Decimal(str(bonus_value))
                        self.sheets.update_shift_field(
                            current_shift_id,
                            "Total made",
                            f"{new_total:.2f}"
                        )
                        logger.info(f"Added flat bonus ${bonus_value} to shift {current_shift_id}")
                else:
                    # No current shift, apply to next shift
                    self.sheets.create_bonus(
                        employee_id,
                        "flat",
                        bonus_value,
                        created_at
                    )

            elif bonus_type in ["paid_day_off", "telegram_premium"]:
                # Special bonuses - just log, no automation
                logger.info(f"Special bonus {bonus_code} awarded to employee {employee_id}")
                # Could create a notification record here if needed

        except Exception as e:
            logger.error(f"Failed to apply rank bonus: {e}")

    def _parse_bonus_code(self, bonus_code: str) -> Tuple[Optional[str], float]:
        """Parse bonus code into type and value.

        Args:
            bonus_code: Bonus code (e.g., 'flat_10', 'percent_next_1').

        Returns:
            Tuple of (bonus_type, value).
        """
        if not bonus_code or bonus_code == "none":
            return None, 0.0

        parts = bonus_code.split("_")

        if parts[0] == "flat":
            # flat_10, flat_25, flat_50, etc.
            if len(parts) >= 2:
                try:
                    value = float(parts[1])
                    return "flat", value
                except ValueError:
                    return None, 0.0

        elif parts[0] == "percent":
            # percent_next_1, percent_prev_1, percent_all_2
            if len(parts) >= 3:
                sub_type = parts[1]  # next, prev, all
                try:
                    value = float(parts[2])

                    if sub_type == "next":
                        return "percent_next", value
                    elif sub_type == "prev":
                        return "percent_prev", value
                    elif sub_type == "all":
                        return "percent_all", value
                except ValueError:
                    return None, 0.0

        elif bonus_code == "double_commission":
            return "double_commission", 0.0

        elif bonus_code == "paid_day_off":
            return "paid_day_off", 0.0

        elif bonus_code == "telegram_premium":
            return "telegram_premium", 0.0

        return None, 0.0

    def format_rank_notification(
        self,
        rank_change: Dict
    ) -> str:
        """Format rank change notification message.

        Args:
            rank_change: Dict with rank change info.

        Returns:
            Formatted message string.
        """
        new_rank = rank_change.get("new_rank", "")
        emoji = rank_change.get("emoji", "")
        bonus = rank_change.get("bonus", "")
        rank_up = rank_change.get("rank_up", True)

        if rank_up:
            # Rank up message
            # Get TEXT from Ranks sheet
            rank_text = self.sheets.get_rank_text(new_rank)

            message = f"🎉 Congratulations!\n\n"
            message += f"Now you're {new_rank} {emoji}\n\n"
            message += f"{rank_text}\n\n"

            if bonus and bonus not in ["none", "paid_day_off", "telegram_premium"]:
                bonus_description = self._format_bonus_description(bonus)
                message += f"As bonus you get:\n\n{bonus_description}"
            elif bonus == "paid_day_off":
                message += "As bonus you get:\n\n🏖️ Pick a Date for Paid Day Off"
            elif bonus == "telegram_premium":
                message += "As bonus you get:\n\n⭐ Telegram Premium for 3 months"

        else:
            # Rank down message
            old_rank = rank_change.get("old_rank", "")
            message = f"📉 Rank Update\n\n"
            message += f"Your rank changed from {old_rank} to {new_rank} {emoji}\n\n"
            message += "Keep pushing to climb back up! 💪"

        return message

    def _format_bonus_description(self, bonus_code: str) -> str:
        """Format bonus description for notification.

        Args:
            bonus_code: Bonus code.

        Returns:
            Human-readable bonus description.
        """
        bonus_type, value = self._parse_bonus_code(bonus_code)

        if bonus_type == "flat":
            return f"💵 Flat bonus +${int(value)}"

        elif bonus_type == "percent_next":
            return f"📈 +{int(value)}% Commission on your next shift"

        elif bonus_type == "percent_prev":
            return f"💰 +{int(value)}% Commission from the chatter from previous shift"

        elif bonus_type == "percent_all":
            return f"🔥 +{int(value)}% from sales of ALL other chatters on your model that day(next shift)"

        elif bonus_type == "double_commission":
            return "⚡ Double commission on your next shift"

        elif bonus_type == "paid_day_off":
            return "🏖️ Pick a Date for Paid Day Off"

        elif bonus_type == "telegram_premium":
            return "⭐ Telegram Premium for 3 months"

        return "🎁 Special bonus"

    def get_all_ranks_info(self) -> str:
        """Get formatted information about all ranks.

        Returns:
            Formatted string with all ranks info.
        """
        ranks = self.sheets.get_ranks()

        if not ranks:
            return "No ranks information available."

        message = "🏆 Rank System\n\n"

        for rank in ranks:
            # Support both SheetsService and PostgresService formats
            rank_name = rank.get("Rank Name") or rank.get("RankName") or rank.get("rank_name") or ""
            min_amt = rank.get("Min Amount") or rank.get("MinTotalSales") or rank.get("min_total_sales") or 0
            max_amt = rank.get("Max Amount") or rank.get("MaxTotalSales") or rank.get("max_total_sales") or 999999
            emoji = rank.get("Emoji") or rank.get("emoji") or ""

            # Format amount range
            if max_amt >= 999999:
                amount_range = f"${int(min_amt):,}+"
            else:
                amount_range = f"${int(min_amt):,} – ${int(max_amt):,}"

            message += f"{rank_name} {emoji} ({amount_range})\n"

            # Format bonuses
            bonuses = [
                rank.get("Bonus 1"),
                rank.get("Bonus 2"),
                rank.get("Bonus 3")
            ]

            if rank_name == "Rookie":
                message += "No bonuses — this is the baseline. Everyone starts here.\n"
            else:
                for idx, bonus in enumerate(bonuses, 1):
                    if bonus and bonus != "none":
                        bonus_desc = self._format_bonus_description(bonus)
                        message += f"{idx}. {bonus_desc}\n"

            message += "\n"

        return message
