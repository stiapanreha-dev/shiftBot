"""Admin command handlers."""

import logging

from telegram import Update
from telegram.ext import ContextTypes

from config import Config
from src.time_utils import now_et
from services.singleton import sheets_service
from services.rank_service import RankService

logger = logging.getLogger(__name__)

ADMIN_IDS = Config.ADMIN_IDS


async def recalc_ranks_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Recalculate ranks for all employees (admin only)."""
    user = update.effective_user

    if user.id not in ADMIN_IDS:
        await update.message.reply_text("⛔ Access denied. Admin only.")
        return

    await update.message.reply_text("🔄 Recalculating ranks...")

    sheets = sheets_service
    now = now_et()
    year, month = now.year, now.month

    try:
        employee_ids = sheets.get_employees_with_activity(year, month)

        updated = 0
        rank_changes = []
        rank_service = RankService(sheets)

        for emp_id in employee_ids:
            rank_change = rank_service.check_and_update_rank(emp_id, year, month)
            updated += 1

            if rank_change and rank_change.get("changed"):
                hush_reward = rank_change.get("hush_reward", 0)
                if hush_reward and hush_reward > 0:
                    new_rank = rank_change.get("new_rank", "")
                    rank_service.apply_hush_reward(emp_id, new_rank, hush_reward)

                rank_changes.append({
                    "employee_id": emp_id,
                    "old_rank": rank_change.get("old_rank"),
                    "new_rank": rank_change.get("new_rank"),
                    "rank_up": rank_change.get("rank_up"),
                    "hush_reward": hush_reward
                })

        report = f"✅ Ranks recalculated for {updated} employees\n\n"

        if rank_changes:
            report += "📊 Rank changes:\n"
            for change in rank_changes:
                direction = "⬆️" if change["rank_up"] else "⬇️"
                hush_text = f" | 🪙 +{change['hush_reward']} HUSH" if change.get("hush_reward") else ""
                report += f"{direction} {change['employee_id']}: {change['old_rank']} → {change['new_rank']}{hush_text}\n"
        else:
            report += "No rank changes detected."

        await update.message.reply_text(report)
        logger.info(f"[ADMIN] User {user.id} recalculated ranks: {len(rank_changes)} changes")

    except Exception as e:
        logger.error(f"[ADMIN] Failed to recalculate ranks: {e}", exc_info=True)
        await update.message.reply_text(f"❌ Error: {e}")


async def withdraw_hush_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Withdraw HUSH coins from employee balance (admin only).

    Usage: /withdraw_hush <employee_id> <amount> [reason]
    """
    user = update.effective_user

    if user.id not in ADMIN_IDS:
        await update.message.reply_text("⛔ Access denied. Admin only.")
        return

    args = context.args
    if len(args) < 2:
        await update.message.reply_text(
            "Usage: /withdraw_hush <employee_id> <amount> [reason]\n"
            "Example: /withdraw_hush 123456789 500 Monthly payout"
        )
        return

    try:
        employee_id = int(args[0])
        amount = int(args[1])
        reason = " ".join(args[2:]) if len(args) > 2 else "Admin withdrawal"

        if amount <= 0:
            await update.message.reply_text("❌ Amount must be positive.")
            return

        sheets = sheets_service

        current_balance = sheets.get_hush_balance(employee_id)

        if current_balance < amount:
            await update.message.reply_text(
                f"❌ Insufficient balance.\n"
                f"Employee {employee_id} has {int(current_balance)} HUSH, "
                f"requested {amount} HUSH."
            )
            return

        tx_id = sheets.withdraw_hush_coins(employee_id, amount, reason)

        new_balance = sheets.get_hush_balance(employee_id)
        dollar_value = amount / 100

        await update.message.reply_text(
            f"✅ Withdrawal successful!\n\n"
            f"Employee: {employee_id}\n"
            f"Amount: {amount} HUSH (${dollar_value:.2f})\n"
            f"Reason: {reason}\n"
            f"New balance: {int(new_balance)} HUSH\n"
            f"TX ID: {tx_id}"
        )

        logger.info(f"[ADMIN] User {user.id} withdrew {amount} HUSH from {employee_id}")

    except ValueError as e:
        await update.message.reply_text(f"❌ Error: {e}")
    except Exception as e:
        logger.error(f"[ADMIN] Failed to withdraw HUSH: {e}", exc_info=True)
        await update.message.reply_text(f"❌ Error: {e}")
