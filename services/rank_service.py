"""Rank system service for managing employee ranks and bonuses."""

import logging
import random
from typing import Optional, Dict, Tuple, TYPE_CHECKING
from datetime import datetime

from src.time_utils import now_et, format_dt

if TYPE_CHECKING:
    from services.postgres_service import PostgresService

logger = logging.getLogger(__name__)


class RankService:
    """Service for managing employee ranks and rank changes."""

    def __init__(self, sheets_service: "PostgresService"):
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
                "hush_reward": 150,  # HUSH coins awarded
                "emoji": "💪"
            }
        """
        try:
            # Determine new rank based on total sales
            new_rank = self.sheets.determine_rank(employee_id, year, month)

            # Get current rank record
            current_record = self.sheets.get_employee_rank(employee_id, year, month)

            if current_record:
                # Get current rank for comparison
                current_rank = current_record.get("Current Rank", "Rookie")
                previous_rank = current_record.get("Previous Rank")
                notified = str(current_record.get("Notified", "false")).lower() == "true"

                # Check if rank changed (compare current_rank with new calculated rank)
                if current_rank != new_rank:
                    # Use previous_rank for notification message (to show what user upgraded FROM)
                    old_rank = previous_rank or current_rank
                    # Rank changed
                    is_rank_up = self._is_rank_up(old_rank, new_rank)

                    # Select random HUSH reward for new rank
                    hush_reward = 0
                    if is_rank_up and new_rank != "Rookie":
                        hush_reward = self._select_random_hush_reward(new_rank)

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

                    logger.info(f"Rank changed for employee {employee_id}: {current_rank} → {new_rank}")

                    # Return notification (update_employee_rank already reset notified=FALSE)
                    return {
                        "changed": True,
                        "old_rank": old_rank,
                        "new_rank": new_rank,
                        "rank_up": is_rank_up,
                        "hush_reward": hush_reward,
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
                    hush_reward = self._select_random_hush_reward(new_rank)
                    emoji = self._get_rank_emoji(new_rank)

                    return {
                        "changed": True,
                        "old_rank": "Rookie",
                        "new_rank": new_rank,
                        "rank_up": True,
                        "hush_reward": hush_reward,
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
        """Select random bonus for rank (LEGACY - kept for backward compatibility).

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

    def _select_random_hush_reward(self, rank_name: str) -> int:
        """Select random HUSH reward for rank.

        Args:
            rank_name: Rank name.

        Returns:
            HUSH coin amount (0 for Rookie).
        """
        if rank_name == "Rookie":
            return 0

        # Get rank_id
        rank_id = self.sheets.get_rank_id_by_name(rank_name)
        if not rank_id:
            logger.warning(f"Rank '{rank_name}' not found")
            return 0

        # Get HUSH rewards for this rank
        rewards = self.sheets.get_hush_rank_rewards(rank_id)

        if rewards:
            # Filter out zeros
            non_zero_rewards = [r for r in rewards if r > 0]
            if non_zero_rewards:
                selected = random.choice(non_zero_rewards)
                logger.info(f"Selected random HUSH reward for {rank_name}: {selected}")
                return selected

        return 0

    def apply_hush_reward(
        self,
        employee_id: int,
        rank_name: str,
        hush_amount: int
    ) -> Optional[int]:
        """Apply HUSH reward to employee balance.

        Args:
            employee_id: Telegram user ID.
            rank_name: New rank name.
            hush_amount: HUSH coins to award.

        Returns:
            Transaction ID or None if no reward.
        """
        if hush_amount <= 0:
            return None

        try:
            # Get rank_id for transaction record
            rank_id = self.sheets.get_rank_id_by_name(rank_name)

            # Add HUSH coins to balance
            tx_id = self.sheets.add_hush_coins(
                employee_id=employee_id,
                amount=hush_amount,
                transaction_type="rank_bonus",
                description=f"Rank up bonus: {rank_name}",
                rank_id=rank_id
            )

            logger.info(f"Applied {hush_amount} HUSH to employee {employee_id} "
                       f"for reaching {rank_name}. TX ID: {tx_id}")

            return tx_id

        except Exception as e:
            logger.error(f"Failed to apply HUSH reward: {e}")
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
        hush_reward = rank_change.get("hush_reward", 0)
        rank_up = rank_change.get("rank_up", True)

        if rank_up:
            # Rank up message
            # Get TEXT from Ranks sheet
            rank_text = self.sheets.get_rank_text(new_rank)

            message = f"🎉 Congratulations!\n\n"
            message += f"Now you're {new_rank} {emoji}\n\n"
            message += f"{rank_text}\n\n"

            if hush_reward > 0:
                # Convert HUSH to dollars (100 HUSH = $1)
                dollar_value = hush_reward / 100
                message += f"As bonus you get:\n\n"
                message += f"🪙 +{hush_reward} HUSH (${dollar_value:.2f})"

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
        """Get formatted information about all ranks with HUSH rewards.

        Returns:
            Formatted string with all ranks info.
        """
        ranks = self.sheets.get_ranks()

        if not ranks:
            return "No ranks information available."

        message = "🏆 Rank System\n\n"
        message += "💰 100 HUSH = $1\n\n"

        for rank in ranks:
            # Support both SheetsService and PostgresService formats
            rank_name = rank.get("Rank Name") or rank.get("RankName") or rank.get("rank_name") or rank.get("name") or ""
            rank_id = rank.get("id") or rank.get("ID")
            min_amt = rank.get("Min Amount") or rank.get("MinTotalSales") or rank.get("min_total_sales") or rank.get("min_amount") or 0
            max_amt = rank.get("Max Amount") or rank.get("MaxTotalSales") or rank.get("max_total_sales") or rank.get("max_amount") or 999999
            emoji = rank.get("Emoji") or rank.get("emoji") or ""

            # Format amount range
            if float(max_amt) >= 999999:
                amount_range = f"${int(float(min_amt)):,}+"
            else:
                amount_range = f"${int(float(min_amt)):,} – ${int(float(max_amt)):,}"

            message += f"{rank_name} {emoji} ({amount_range})\n"

            if rank_name == "Rookie":
                message += "No bonuses — this is the baseline. Everyone starts here.\n"
            else:
                # Get HUSH rewards for this rank
                if rank_id:
                    rewards = self.sheets.get_hush_rank_rewards(rank_id)
                    if rewards:
                        non_zero = [r for r in rewards if r > 0]
                        if non_zero:
                            rewards_str = ", ".join([f"🪙 {r}" for r in non_zero])
                            message += f"Possible HUSH rewards: {rewards_str}\n"

            message += "\n"

        return message
