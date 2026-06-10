"""Statistics, ranks info, and HUSH balance handlers."""

import logging
from decimal import Decimal

from telegram import Update
from telegram.ext import ContextTypes

from config import START
from src.time_utils import now_et
from services.singleton import sheets_service
from services.rank_service import RankService
from src.keyboards import start_menu_keyboard
from src.handlers.navigation import remove_keyboard

logger = logging.getLogger(__name__)


async def show_statistics(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Show user statistics (rank, sales, pay day)."""
    query = update.callback_query
    await query.answer()
    await remove_keyboard(query)

    user = update.effective_user

    try:
        logger.info(f"[STATS] User {user.id} viewing statistics")
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

        sheets = sheets_service
        rank_service = RankService(sheets)

        now = now_et()
        year = now.year
        month = now.month

        rank_record = sheets.get_employee_rank(user.id, year, month)
        if rank_record:
            current_rank = rank_record.get("Current Rank", "Rookie")
        else:
            current_rank = sheets.determine_rank(user.id, year, month)

        rank_emoji = rank_service._get_rank_emoji(current_rank)

        if now.day <= 15:
            current_fortnight = 1
            next_pay_day = now.replace(day=16)
        else:
            current_fortnight = 2
            if month == 12:
                next_pay_day = now.replace(year=year+1, month=1, day=1)
            else:
                next_pay_day = now.replace(month=month+1, day=1)

        bonus_count = 0
        bonus_amount = Decimal("0")

        try:
            fortnights = sheets.get_employee_fortnights(user.id, year, month)
            for f in fortnights:
                if f.get('fortnight') == current_fortnight:
                    bonus_count = f.get('bonus_counter_true_count', 0) or 0
                    bonus_amount = Decimal(str(f.get('bonus_amount', 0) or 0))
                    break
        except Exception as e:
            logger.warning(f"Failed to get fortnight data: {e}")

        if current_fortnight == 1:
            start_day, end_day = 1, 15
        else:
            start_day, end_day = 16, 31

        month_stats = sheets.get_employee_month_stats(
            user.id, year, month, start_day, end_day
        )
        total_sales_month = month_stats['month_sales']
        total_made_since_payday = month_stats['fortnight_made']

        total_with_bonus = total_made_since_payday + bonus_amount

        hush_balance = sheets.get_hush_balance(user.id)
        hush_dollar_value = float(hush_balance) / 100

        message = f"📊 Your Statistics\n\n"
        message += f"🏆 Rank: {current_rank} {rank_emoji}\n"
        message += f"🪙 HUSH Balance: {int(hush_balance)} (${hush_dollar_value:.2f})\n"
        message += f"💰 Total sales this month: ${total_sales_month:.2f}\n"
        message += f"💵 Total made since last pay day: ${total_with_bonus:.2f}\n"
        message += f"✨ Current applied bonus: +{bonus_count}% (${bonus_amount:.2f})\n"
        message += f"📅 Next pay day: {next_pay_day.strftime('%B %d, %Y')}\n\n"
        message += "Keep it up! 🚀"

        sent_msg = await query.message.reply_text(message, reply_markup=start_menu_keyboard())
        context.user_data["last_keyboard_message_id"] = sent_msg.message_id

        return START

    except Exception as e:
        logger.error(f"[ERROR] Failed to show statistics for user {user.id}: {e}", exc_info=True)
        sent_msg = await query.message.reply_text(
            "❌ Error loading statistics.\n"
            "Please try again later.",
            reply_markup=start_menu_keyboard()
        )
        context.user_data["last_keyboard_message_id"] = sent_msg.message_id
        return START


async def show_ranks_info(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Show information about rank system."""
    query = update.callback_query
    await query.answer()
    await remove_keyboard(query)

    user = update.effective_user

    try:
        logger.info(f"[RANKS] User {user.id} viewing ranks info")

        sheets = sheets_service
        rank_service = RankService(sheets)

        ranks_info = rank_service.get_all_ranks_info()

        sent_msg = await query.message.reply_text(ranks_info, reply_markup=start_menu_keyboard())
        context.user_data["last_keyboard_message_id"] = sent_msg.message_id

        return START

    except Exception as e:
        logger.error(f"[ERROR] Failed to show ranks info for user {user.id}: {e}", exc_info=True)
        sent_msg = await query.message.reply_text(
            "❌ Error loading ranks information.\n"
            "Please try again later.",
            reply_markup=start_menu_keyboard()
        )
        context.user_data["last_keyboard_message_id"] = sent_msg.message_id
        return START


async def show_hush_balance(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Show HUSH coin balance and transaction history."""
    query = update.callback_query
    await query.answer()
    await remove_keyboard(query)

    user = update.effective_user

    try:
        logger.info(f"[HUSH] User {user.id} viewing HUSH balance")

        sheets = sheets_service

        balance = sheets.get_hush_balance(user.id)
        dollar_value = float(balance) / 100

        transactions = sheets.get_hush_transactions(user.id, limit=5)

        message = "🪙 HUSH Balance\n\n"
        message += f"Current balance: {int(balance)} HUSH (${dollar_value:.2f})\n\n"

        if transactions:
            message += "📋 Recent transactions:\n"
            for tx in transactions:
                amount = int(tx.get('amount', 0))
                tx_type = tx.get('transaction_type', '')
                rank_name = tx.get('rank_name', '')
                created_at = tx.get('created_at', '')

                if created_at:
                    if hasattr(created_at, 'strftime'):
                        date_str = created_at.strftime('%d.%m.%Y')
                    else:
                        date_str = str(created_at)[:10]
                else:
                    date_str = ''

                if amount >= 0:
                    sign = "+"
                else:
                    sign = ""

                if tx_type == 'rank_bonus' and rank_name:
                    message += f"  {sign}{amount} HUSH - {rank_name} ({date_str})\n"
                elif tx_type == 'withdrawal':
                    message += f"  {sign}{amount} HUSH - Withdrawal ({date_str})\n"
                else:
                    message += f"  {sign}{amount} HUSH ({date_str})\n"
        else:
            message += "No transactions yet.\n"

        message += "\n💰 100 HUSH = $1"

        sent_msg = await query.message.reply_text(message, reply_markup=start_menu_keyboard())
        context.user_data["last_keyboard_message_id"] = sent_msg.message_id

        return START

    except Exception as e:
        logger.error(f"[ERROR] Failed to show HUSH balance for user {user.id}: {e}", exc_info=True)
        sent_msg = await query.message.reply_text(
            "❌ Error loading HUSH balance.\n"
            "Please try again later.",
            reply_markup=start_menu_keyboard()
        )
        context.user_data["last_keyboard_message_id"] = sent_msg.message_id
        return START
