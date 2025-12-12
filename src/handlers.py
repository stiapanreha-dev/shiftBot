"""Handlers for Telegram bot shift tracking."""

import logging
from decimal import Decimal, InvalidOperation
from datetime import timedelta
from typing import Dict

from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler

from config import Config, START, CHOOSE_DATE_IN, CHOOSE_TIME_IN, CHOOSE_TIME_OUT
from config import PICK_PRODUCT, ENTER_AMOUNT, ADD_OR_FINISH
from config import EDIT_MENU, EDIT_PICK_SHIFT, EDIT_FIELD
from config import EDIT_DATE_IN, EDIT_TIME_IN, EDIT_DATE_OUT, EDIT_TIME_OUT, EDIT_TOTAL_SALES

from src.time_utils import (
    now_et, format_dt, hour_from_label, create_datetime_from_date_and_hour,
    parse_dt, get_server_date
)
from services.singleton import sheets_service  # Use singleton instance with caching
from services.rank_service import RankService
from src.keyboards import (
    date_choice_keyboard, date_choice_edit_keyboard, time_keyboard,
    products_keyboard, add_or_finish_keyboard, start_menu_keyboard,
    edit_fields_keyboard, shifts_list_keyboard, claim_rank_button
)

logger = logging.getLogger(__name__)

# Admin user IDs for privileged commands
ADMIN_IDS = [7867347055, 2125295046, 8152358885, 7367062056]


# =============================================================================
# UTILITIES
# =============================================================================

def push_state(context: ContextTypes.DEFAULT_TYPE, state: int) -> None:
    """Push state to navigation stack.

    Args:
        context: Bot context.
        state: State to push.
    """
    stack = context.user_data.setdefault("stack", [])
    stack.append(state)


def go_back(context: ContextTypes.DEFAULT_TYPE) -> int:
    """Pop current state and return previous.

    Args:
        context: Bot context.

    Returns:
        Previous state.
    """
    stack = context.user_data.get("stack", [START])

    if len(stack) > 1:
        stack.pop()  # Remove current
        return stack[-1]

    return START


def reset_flow(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Reset user data and navigation stack, but preserve user identity.

    Args:
        context: Bot context.
    """
    # Preserve user identity and chat info
    employee_id = context.user_data.get("employee_id")
    employee_name = context.user_data.get("employee_name")
    chat_id = context.user_data.get("chat_id")

    # Clear all data
    context.user_data.clear()

    # Restore user identity and chat info
    context.user_data["stack"] = [START]
    if employee_id is not None:
        context.user_data["employee_id"] = employee_id
    if employee_name is not None:
        context.user_data["employee_name"] = employee_name
    if chat_id is not None:
        context.user_data["chat_id"] = chat_id


async def remove_keyboard(query) -> None:
    """Safely remove inline keyboard from message.

    Args:
        query: CallbackQuery object.
    """
    try:
        await query.edit_message_reply_markup(reply_markup=None)
    except Exception as e:
        # Ignore errors (e.g., message not modified, message too old)
        logger.debug(f"Could not remove keyboard: {e}")


async def remove_last_keyboard(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Remove inline keyboard from last bot message.

    Args:
        context: Bot context.
    """
    last_msg_id = context.user_data.get("last_keyboard_message_id")
    chat_id = context.user_data.get("chat_id")

    if last_msg_id and chat_id:
        try:
            await context.bot.edit_message_reply_markup(
                chat_id=chat_id,
                message_id=last_msg_id,
                reply_markup=None
            )
            logger.debug(f"Removed keyboard from message {last_msg_id}")
        except Exception as e:
            logger.debug(f"Could not remove last keyboard: {e}")
        finally:
            # Clear saved message ID
            context.user_data.pop("last_keyboard_message_id", None)


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

    Args:
        employee_id: Employee ID.
        commission_pct: Total commission percentage (can be float or string).
        shift_id: Shift ID (optional, for getting applied bonuses).

    Returns:
        Formatted commission breakdown string.
    """
    sheets = sheets_service

    # Ensure commission_pct is float
    commission_pct = float(commission_pct)

    # Get tier info (NEW - uses base_commissions table)
    tier_name = "Tier C"
    base_commission = 6.0
    try:
        tier = sheets.get_employee_tier(employee_id)
        if tier:
            tier_name = tier.get('name', 'Tier C')
            base_commission = float(tier.get('percentage', 6.0))
    except Exception:
        # Fallback to old method if get_employee_tier not available
        try:
            settings = sheets.get_employee_settings(employee_id)
            base_commission = float(settings.get("Sales commission", 6.0))
            tier_name = f"Base"
        except Exception:
            pass

    # Get bonus percentage if shift_id provided
    bonus_pct = 0.0
    if shift_id:
        try:
            applied_bonuses = sheets.get_shift_applied_bonuses(shift_id)

            # Sum percent_next bonuses
            for bonus in applied_bonuses:
                if bonus.get("Bonus Type") == "percent_next":
                    bonus_pct += float(bonus.get("Value", 0))
        except Exception as e:
            logger.error(f"Failed to get bonus breakdown: {e}")

    # Format the breakdown string
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

    # Get rolling average and bonus counter (NEW)
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

    # Add rolling average and bonus counter info (NEW)
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
    # Products are stored in database
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
        sheets = sheets_service
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
        try:
            applied_bonuses = sheets.get_shift_applied_bonuses(shift_id)

            # Filter bonuses that apply to shifts (percent_next, percent_all)
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
                from rank_service import RankService
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
            # Don't fail the whole summary if bonus info fails

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


# =============================================================================
# START HANDLER
# =============================================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle /start command.

    Args:
        update: Telegram update.
        context: Bot context.

    Returns:
        Next state.
    """
    reset_flow(context)

    user = update.effective_user
    context.user_data["employee_id"] = user.id
    context.user_data["employee_name"] = user.username or user.full_name or f"user_{user.id}"
    context.user_data["products"] = {}
    context.user_data["time_daypart_in"] = "AM"
    context.user_data["time_daypart_out"] = "AM"
    context.user_data["chat_id"] = update.effective_chat.id

    logger.info(f"[START] User {user.id} (@{user.username}) started bot")

    sent_msg = await update.message.reply_text(
        "Welcome to Shift Tracking Bot!\n\nChoose an action:",
        reply_markup=start_menu_keyboard()
    )

    # Save keyboard message ID
    context.user_data["last_keyboard_message_id"] = sent_msg.message_id

    return START


# =============================================================================
# SHIFT CREATION HANDLERS
# =============================================================================

async def start_create_shift(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start shift creation flow.

    Args:
        update: Telegram update.
        context: Bot context.

    Returns:
        Next state.
    """
    query = update.callback_query
    await query.answer()
    await remove_keyboard(query)

    user = update.effective_user
    logger.info(f"[CREATE] User {user.id} started shift creation")

    # Initialize products dictionary if not exists
    if "products" not in context.user_data:
        context.user_data["products"] = {}

    push_state(context, CHOOSE_DATE_IN)

    sent_msg = await query.message.reply_text(
        "Choose shift start date:",
        reply_markup=date_choice_keyboard()
    )

    # Save keyboard message ID
    context.user_data["last_keyboard_message_id"] = sent_msg.message_id

    return CHOOSE_DATE_IN


async def handle_date_choice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle date choice for Clock in.

    Args:
        update: Telegram update.
        context: Bot context.

    Returns:
        Next state.
    """
    query = update.callback_query
    await query.answer()
    await remove_keyboard(query)

    _, offset_str = query.data.split(":")
    offset = int(offset_str)

    date, date_str = get_server_date(offset)
    context.user_data["clock_in_date"] = date
    context.user_data["time_daypart_in"] = "AM"

    user = update.effective_user
    logger.info(f"[DATE] User {user.id} selected date: {date_str} (offset: {offset})")

    push_state(context, CHOOSE_TIME_IN)

    sent_msg = await query.message.reply_text(
        "Choose shift start time:",
        reply_markup=time_keyboard("IN", "AM")
    )

    # Save keyboard message ID
    context.user_data["last_keyboard_message_id"] = sent_msg.message_id

    return CHOOSE_TIME_IN


async def handle_time_switch(update: Update, context: ContextTypes.DEFAULT_TYPE, kind: str, daypart: str) -> int:
    """Handle AM/PM switch.

    Args:
        update: Telegram update.
        context: Bot context.
        kind: 'IN' or 'OUT'.
        daypart: 'AM' or 'PM'.

    Returns:
        Current state.
    """
    query = update.callback_query
    await query.answer()

    if kind == "IN":
        context.user_data["time_daypart_in"] = daypart
        await query.edit_message_reply_markup(reply_markup=time_keyboard("IN", daypart))
        return CHOOSE_TIME_IN
    else:
        context.user_data["time_daypart_out"] = daypart
        await query.edit_message_reply_markup(reply_markup=time_keyboard("OUT", daypart))
        return CHOOSE_TIME_OUT


async def handle_time_choice_in(update: Update, context: ContextTypes.DEFAULT_TYPE, label: str) -> int:
    """Handle time choice for Clock in.

    Args:
        update: Telegram update.
        context: Bot context.
        label: Time label (e.g., '9 AM').

    Returns:
        Next state.
    """
    query = update.callback_query
    await query.answer()
    await remove_keyboard(query)

    hour = hour_from_label(label)
    date = context.user_data["clock_in_date"]
    dt = create_datetime_from_date_and_hour(date, hour)

    context.user_data["clock_in"] = format_dt(dt)
    context.user_data["clock_in_dt"] = dt

    user = update.effective_user
    logger.info(f"[TIME_IN] User {user.id} selected Clock in: {format_dt(dt)}")

    # Clock out date = current server date
    clock_out_date, _ = get_server_date(0)
    context.user_data["clock_out_date"] = clock_out_date
    context.user_data["time_daypart_out"] = "AM"

    push_state(context, CHOOSE_TIME_OUT)

    sent_msg = await query.message.reply_text(
        "Choose shift end time:",
        reply_markup=time_keyboard("OUT", "AM")
    )

    # Save keyboard message ID
    context.user_data["last_keyboard_message_id"] = sent_msg.message_id

    return CHOOSE_TIME_OUT


async def handle_time_choice_out(update: Update, context: ContextTypes.DEFAULT_TYPE, label: str) -> int:
    """Handle time choice for Clock out.

    Args:
        update: Telegram update.
        context: Bot context.
        label: Time label (e.g., '5 PM').

    Returns:
        Next state.
    """
    query = update.callback_query
    await query.answer()
    await remove_keyboard(query)

    hour = hour_from_label(label)
    date = context.user_data["clock_out_date"]
    dt = create_datetime_from_date_and_hour(date, hour)

    context.user_data["clock_out"] = format_dt(dt)
    context.user_data["clock_out_dt"] = dt

    user = update.effective_user

    # Validate: Clock out must be after Clock in
    clock_in_dt = context.user_data.get("clock_in_dt")
    if dt <= clock_in_dt:
        logger.warning(f"[TIME_OUT] User {user.id} selected Clock out before Clock in: {format_dt(dt)}")
        sent_msg = await query.message.reply_text(
            "⚠️ Error: End time must be after start time!\n"
            "Please choose a later time.",
            reply_markup=time_keyboard("OUT", context.user_data["time_daypart_out"])
        )
        # Save keyboard message ID
        context.user_data["last_keyboard_message_id"] = sent_msg.message_id
        return CHOOSE_TIME_OUT

    logger.info(f"[TIME_OUT] User {user.id} selected Clock out: {format_dt(dt)}")

    push_state(context, PICK_PRODUCT)

    sent_msg = await query.message.reply_text(
        "Choose product:",
        reply_markup=products_keyboard()
    )

    # Save keyboard message ID
    context.user_data["last_keyboard_message_id"] = sent_msg.message_id

    return PICK_PRODUCT


async def handle_product_choice(update: Update, context: ContextTypes.DEFAULT_TYPE, product: str) -> int:
    """Handle product selection.

    Args:
        update: Telegram update.
        context: Bot context.
        product: Product name.

    Returns:
        Next state.
    """
    query = update.callback_query
    await query.answer()
    await remove_keyboard(query)

    user = update.effective_user

    # Check duplicate
    if product in context.user_data.get("products", {}):
        logger.warning(f"[PRODUCT] User {user.id} tried to add duplicate product: {product}")
        await query.answer("⚠️ This product already added!", show_alert=True)
        sent_msg = await query.message.reply_text(
            f"Product '{product}' already added.\nChoose another product:",
            reply_markup=products_keyboard(exclude=list(context.user_data["products"].keys()))
        )
        # Save keyboard message ID
        context.user_data["last_keyboard_message_id"] = sent_msg.message_id
        return PICK_PRODUCT

    logger.info(f"[PRODUCT] User {user.id} selected product: {product}")
    context.user_data["current_product"] = product

    await query.message.reply_text(
        f"Enter sales amount for '{product}':\n(e.g., 99.90)"
    )

    return ENTER_AMOUNT


async def handle_amount_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle amount input.

    Args:
        update: Telegram update.
        context: Bot context.

    Returns:
        Next state.
    """
    text = update.message.text.strip()
    user = update.effective_user

    try:
        amount = parse_amount(text)

        if amount < 0:
            raise ValueError("Negative amount")

    except (InvalidOperation, ValueError):
        logger.warning(f"[AMOUNT] User {user.id} entered invalid amount: {text}")
        await update.message.reply_text(
            "❌ Invalid amount. Please enter a positive number (e.g., 123.45):"
        )
        return ENTER_AMOUNT

    product = context.user_data["current_product"]

    # Ensure products dict exists
    if "products" not in context.user_data:
        context.user_data["products"] = {}

    context.user_data["products"][product] = amount

    logger.info(f"[AMOUNT] User {user.id} entered amount for {product}: {amount}")

    push_state(context, ADD_OR_FINISH)

    # Show summary of added products
    summary_lines = ["Product added:", f"• {product}: {amount:.2f}", ""]

    if len(context.user_data["products"]) > 1:
        summary_lines.append("All products:")
        for p, a in context.user_data["products"].items():
            summary_lines.append(f"• {p}: {a:.2f}")
        summary_lines.append("")

    summary_lines.append("Add more products or finish shift?")

    sent_msg = await update.message.reply_text(
        "\n".join(summary_lines),
        reply_markup=add_or_finish_keyboard()
    )

    # Save keyboard message ID
    context.user_data["last_keyboard_message_id"] = sent_msg.message_id

    return ADD_OR_FINISH


async def handle_add_model(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle Add model button.

    Args:
        update: Telegram update.
        context: Bot context.

    Returns:
        Next state.
    """
    query = update.callback_query
    await query.answer()
    await remove_keyboard(query)

    push_state(context, PICK_PRODUCT)

    # Show already added products
    added = context.user_data.get("products", {})
    message = "Already added:\n"

    for product, amount in added.items():
        message += f"• {product}: {amount:.2f}\n"

    message += "\nChoose next product:"

    sent_msg = await query.message.reply_text(
        message,
        reply_markup=products_keyboard(exclude=list(added.keys()))
    )

    # Save keyboard message ID
    context.user_data["last_keyboard_message_id"] = sent_msg.message_id

    return PICK_PRODUCT


async def check_and_notify_rank(
    user_id: int,
    shift_id: int,
    context: ContextTypes.DEFAULT_TYPE,
    message
) -> None:
    """Check for rank changes and send notification.

    Args:
        user_id: Telegram user ID.
        shift_id: Created shift ID.
        context: Bot context.
        message: Message object to reply to.
    """
    try:
        sheets = sheets_service
        rank_service = RankService(sheets)

        # Get year/month from the shift date (not current date!)
        shift = sheets.get_shift_by_id(shift_id)
        if shift:
            # Parse shift date to get year and month
            shift_date_str = shift.get('date') or shift.get('shift_date') or shift.get('Date')
            if shift_date_str:
                # Handle both datetime and date formats
                date_part = str(shift_date_str).split()[0]  # "2025-11-30 00:00:00" -> "2025-11-30"
                date_part = date_part.replace("/", "-")  # Normalize format
                parts = date_part.split("-")
                year = int(parts[0])
                month = int(parts[1])
            else:
                # Fallback to current date
                now = now_et()
                year = now.year
                month = now.month
        else:
            # Fallback to current date if shift not found
            now = now_et()
            year = now.year
            month = now.month

        # Check for rank change
        rank_change = rank_service.check_and_update_rank(user_id, year, month)

        if rank_change and rank_change.get("changed"):
            # Rank changed - send notification
            notification = rank_service.format_rank_notification(rank_change)
            sent_msg = await message.reply_text(
                notification,
                reply_markup=claim_rank_button()
            )

            # Save keyboard message ID
            context.user_data["last_keyboard_message_id"] = sent_msg.message_id

            # Apply bonus if available
            bonus = rank_change.get("bonus")
            if bonus:
                rank_service.apply_rank_bonus(user_id, bonus, shift_id)

            # Mark as notified
            sheets.mark_rank_notified(user_id, year, month)

            logger.info(
                f"[RANK] User {user_id} rank changed: "
                f"{rank_change.get('old_rank')} → {rank_change.get('new_rank')}"
            )

    except Exception as e:
        logger.error(f"[ERROR] Failed to check rank for user {user_id}: {e}", exc_info=True)
        # Don't fail the whole flow if rank check fails


async def handle_finish_shift(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle Finish shift button - save to Google Sheets.

    Args:
        update: Telegram update.
        context: Bot context.

    Returns:
        End of conversation.
    """
    query = update.callback_query
    await query.answer()
    await remove_keyboard(query)

    user = update.effective_user

    try:
        logger.info(f"[SAVE] User {user.id} finishing shift creation")

        # Show typing indicator while saving to Sheets
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

        sheets = sheets_service

        shift_data = {
            "date": format_dt(now_et()),
            "employee_id": context.user_data["employee_id"],
            "employee_name": context.user_data["employee_name"],
            "clock_in": context.user_data["clock_in"],
            "clock_out": context.user_data["clock_out"],
            "products": context.user_data["products"],
        }

        # Calculate totals for logging
        total_sales = sum(Decimal(str(v)) for v in shift_data["products"].values())
        products_str = ", ".join([f"{k}:{v}" for k, v in shift_data["products"].items()])

        shift_id = sheets.create_shift(shift_data)

        # Get created shift data for accurate totals
        created_shift = sheets.get_shift_by_id(shift_id)

        summary = build_summary(shift_data, shift_id, created_shift)

        # Import main_menu_button here to avoid circular import
        from src.keyboards import main_menu_button

        sent_msg = await query.message.reply_text(summary, reply_markup=main_menu_button())
        # Save keyboard message ID
        context.user_data["last_keyboard_message_id"] = sent_msg.message_id

        logger.info(
            f"[SAVED] Shift {shift_id} created for user {user.id} | "
            f"Clock in: {shift_data['clock_in']} | "
            f"Clock out: {shift_data['clock_out']} | "
            f"Products: {products_str} | "
            f"Total: {total_sales}"
        )

        # Check and notify rank changes
        await check_and_notify_rank(user.id, shift_id, context, query.message)

        reset_flow(context)

        return START

    except Exception as e:
        logger.error(f"[ERROR] Failed to create shift for user {user.id}: {e}", exc_info=True)
        await query.message.reply_text(
            "❌ Error saving shift to Google Sheets.\n"
            "Please try again later or contact administrator."
        )
        return ConversationHandler.END


# =============================================================================
# SHIFT EDITING HANDLERS
# =============================================================================

async def start_edit_shift(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start shift editing flow - show last 3 shifts.

    Args:
        update: Telegram update.
        context: Bot context.

    Returns:
        Next state.
    """
    query = update.callback_query
    await query.answer()
    await remove_keyboard(query)

    user = update.effective_user

    try:
        logger.info(f"[EDIT] User {user.id} started shift editing")

        # Show typing indicator while loading from Sheets
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

        sheets = sheets_service
        employee_id = context.user_data["employee_id"]

        shifts = sheets.get_last_shifts(employee_id, limit=3)

        if not shifts:
            logger.info(f"[EDIT] User {user.id} has no shifts to edit")
            await query.message.reply_text(
                "No shifts found to edit.\n\nUse /start to create your first shift."
            )
            return ConversationHandler.END

        logger.info(f"[EDIT] User {user.id} viewing {len(shifts)} shifts")

        push_state(context, EDIT_PICK_SHIFT)

        sent_msg = await query.message.reply_text(
            "Select shift to edit:",
            reply_markup=shifts_list_keyboard(shifts)
        )
        # Save keyboard message ID
        context.user_data["last_keyboard_message_id"] = sent_msg.message_id

        return EDIT_PICK_SHIFT

    except Exception as e:
        logger.error(f"[ERROR] Failed to get shifts for editing for user {user.id}: {e}", exc_info=True)
        await query.message.reply_text(
            "❌ Error loading shifts.\nPlease try again later."
        )
        return ConversationHandler.END


async def handle_edit_pick_shift(update: Update, context: ContextTypes.DEFAULT_TYPE, shift_id: int) -> int:
    """Handle shift selection for editing.

    Args:
        update: Telegram update.
        context: Bot context.
        shift_id: Selected shift ID.

    Returns:
        Next state.
    """
    query = update.callback_query
    await query.answer()
    await remove_keyboard(query)

    try:
        # Show typing indicator while loading shift
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

        sheets = sheets_service
        shift = sheets.get_shift_by_id(shift_id)

        if not shift:
            await query.message.reply_text(
                "❌ Shift not found. It may have been deleted."
            )
            return ConversationHandler.END

        context.user_data["edit_shift_id"] = shift_id
        context.user_data["edit_shift_data"] = shift

        push_state(context, EDIT_FIELD)

        sent_msg = await query.message.reply_text(
            f"Editing shift ID {shift_id}\n\nSelect field to edit:",
            reply_markup=edit_fields_keyboard()
        )
        # Save keyboard message ID
        context.user_data["last_keyboard_message_id"] = sent_msg.message_id

        return EDIT_FIELD

    except Exception as e:
        logger.error(f"Failed to load shift {shift_id}: {e}")
        await query.message.reply_text(
            "❌ Error loading shift.\nPlease try again later."
        )
        return ConversationHandler.END


async def handle_edit_field_choice(update: Update, context: ContextTypes.DEFAULT_TYPE, field: str) -> int:
    """Handle field choice for editing.

    Args:
        update: Telegram update.
        context: Bot context.
        field: Field to edit ('IN', 'OUT', 'TOTAL').

    Returns:
        Next state.
    """
    query = update.callback_query
    await query.answer()
    await remove_keyboard(query)

    context.user_data["edit_field"] = field
    shift_data = context.user_data["edit_shift_data"]

    if field == "IN":
        # Edit Clock in - choose date relative to record Date
        record_date_str = shift_data.get("Date", "")
        record_date_str = str(record_date_str).replace("-", "/")
        record_date = parse_dt(record_date_str).date()
        context.user_data["edit_record_date"] = record_date

        push_state(context, EDIT_DATE_IN)

        sent_msg = await query.message.reply_text(
            f"Record date: {record_date_str}\n\nChoose date for Clock in:",
            reply_markup=date_choice_edit_keyboard()
        )
        # Save keyboard message ID
        context.user_data["last_keyboard_message_id"] = sent_msg.message_id

        return EDIT_DATE_IN

    elif field == "OUT":
        # Edit Clock out - use date from record Date
        record_date_str = shift_data.get("Date", "")
        record_date_str = str(record_date_str).replace("-", "/")
        record_date = parse_dt(record_date_str).date()
        context.user_data["edit_record_date"] = record_date
        context.user_data["clock_out_date"] = record_date
        context.user_data["time_daypart_out"] = "AM"

        push_state(context, EDIT_TIME_OUT)

        sent_msg = await query.message.reply_text(
            "Choose time for Clock out:",
            reply_markup=time_keyboard("OUT", "AM", mode="edit")
        )
        # Save keyboard message ID
        context.user_data["last_keyboard_message_id"] = sent_msg.message_id

        return EDIT_TIME_OUT

    else:  # TOTAL
        push_state(context, EDIT_TOTAL_SALES)

        await query.message.reply_text(
            f"Current Total sales: {shift_data.get('Total sales', '0.00')}\n\n"
            "Enter new Total sales amount (e.g., 350.00):"
        )

        return EDIT_TOTAL_SALES


async def handle_edit_date_choice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle date choice when editing Clock in.

    Args:
        update: Telegram update.
        context: Bot context.

    Returns:
        Next state.
    """
    query = update.callback_query
    await query.answer()
    await remove_keyboard(query)

    _, offset_str = query.data.split(":")
    offset = int(offset_str)

    record_date = context.user_data["edit_record_date"]
    selected_date = record_date + timedelta(days=offset)

    context.user_data["clock_in_date"] = selected_date
    context.user_data["time_daypart_in"] = "AM"

    push_state(context, EDIT_TIME_IN)

    sent_msg = await query.message.reply_text(
        f"Selected date: {selected_date.strftime('%Y/%m/%d')}\n\n"
        "Choose time for Clock in:",
        reply_markup=time_keyboard("IN", "AM", mode="edit")
    )
    # Save keyboard message ID
    context.user_data["last_keyboard_message_id"] = sent_msg.message_id

    return EDIT_TIME_IN


async def handle_edit_time_in(update: Update, context: ContextTypes.DEFAULT_TYPE, label: str) -> int:
    """Handle time choice when editing Clock in.

    Args:
        update: Telegram update.
        context: Bot context.
        label: Time label.

    Returns:
        End of conversation.
    """
    query = update.callback_query
    await query.answer()

    try:
        hour = hour_from_label(label)
        date = context.user_data["clock_in_date"]
        dt = create_datetime_from_date_and_hour(date, hour)
        clock_in_str = format_dt(dt)

        # Show typing indicator while updating Sheets
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

        sheets = sheets_service
        shift_id = context.user_data["edit_shift_id"]

        success = sheets.update_shift_field(shift_id, "Clock in", clock_in_str)

        if success:
            # Recalculate worked hours after time change
            sheets.recalculate_worked_hours(shift_id)

            from src.keyboards import main_menu_button

            # Get updated shift data
            updated_shift = sheets.get_shift_by_id(shift_id)

            if updated_shift:
                # Get employee ID
                employee_id = context.user_data.get("employee_id")

                # Format detailed shift information
                shift_details = format_shift_details(updated_shift, employee_id, shift_id)

                sent_msg = await query.message.reply_text(
                    shift_details,
                    reply_markup=main_menu_button()
                )
                # Save keyboard message ID
                context.user_data["last_keyboard_message_id"] = sent_msg.message_id
            else:
                sent_msg = await query.message.reply_text(
                    f"✅ Clock in updated to: {clock_in_str}",
                    reply_markup=main_menu_button()
                )
                context.user_data["last_keyboard_message_id"] = sent_msg.message_id

            logger.info(f"[UPDATED] Shift {shift_id} Clock in updated to {clock_in_str} by user {update.effective_user.id}")
        else:
            logger.warning(f"[EDIT] Failed to update shift {shift_id} - not found")
            await query.message.reply_text(
                "❌ Failed to update shift. It may have been deleted."
            )

        reset_flow(context)
        return START

    except Exception as e:
        logger.error(f"Failed to update Clock in: {e}")
        await query.message.reply_text(
            "❌ Error updating shift.\nPlease try again later."
        )
        return START


async def handle_edit_time_out(update: Update, context: ContextTypes.DEFAULT_TYPE, label: str) -> int:
    """Handle time choice when editing Clock out.

    Args:
        update: Telegram update.
        context: Bot context.
        label: Time label.

    Returns:
        End of conversation.
    """
    query = update.callback_query
    await query.answer()

    try:
        hour = hour_from_label(label)
        date = context.user_data["clock_out_date"]
        dt = create_datetime_from_date_and_hour(date, hour)
        clock_out_str = format_dt(dt)

        # Show typing indicator while updating Sheets
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

        sheets = sheets_service
        shift_id = context.user_data["edit_shift_id"]

        success = sheets.update_shift_field(shift_id, "Clock out", clock_out_str)

        if success:
            # Recalculate worked hours after time change
            sheets.recalculate_worked_hours(shift_id)

            from src.keyboards import main_menu_button

            # Get updated shift data
            updated_shift = sheets.get_shift_by_id(shift_id)

            if updated_shift:
                # Get employee ID
                employee_id = context.user_data.get("employee_id")

                # Format detailed shift information
                shift_details = format_shift_details(updated_shift, employee_id, shift_id)

                sent_msg = await query.message.reply_text(
                    shift_details,
                    reply_markup=main_menu_button()
                )
                # Save keyboard message ID
                context.user_data["last_keyboard_message_id"] = sent_msg.message_id
            else:
                sent_msg = await query.message.reply_text(
                    f"✅ Clock out updated to: {clock_out_str}",
                    reply_markup=main_menu_button()
                )
                context.user_data["last_keyboard_message_id"] = sent_msg.message_id

            logger.info(f"[UPDATED] Shift {shift_id} Clock out updated to {clock_out_str} by user {update.effective_user.id}")
        else:
            logger.warning(f"[EDIT] Failed to update shift {shift_id} - not found")
            await query.message.reply_text(
                "❌ Failed to update shift. It may have been deleted."
            )

        reset_flow(context)
        return START

    except Exception as e:
        logger.error(f"Failed to update Clock out: {e}")
        await query.message.reply_text(
            "❌ Error updating shift.\nPlease try again later."
        )
        return START


async def handle_edit_total_sales_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle Total sales input when editing.

    Args:
        update: Telegram update.
        context: Bot context.

    Returns:
        End of conversation.
    """
    text = update.message.text.strip()

    try:
        amount = parse_amount(text)

        if amount < 0:
            raise ValueError("Negative amount")

        # Show typing indicator while updating Sheets
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

        sheets = sheets_service
        shift_id = context.user_data["edit_shift_id"]

        success = sheets.update_total_sales(shift_id, amount)

        if success:
            # Get updated shift data to show correct calculated values
            updated_shift = sheets.get_shift_by_id(shift_id)

            if updated_shift:
                from src.keyboards import main_menu_button

                # Get employee ID
                employee_id = context.user_data.get("employee_id")

                # Format detailed shift information
                shift_details = format_shift_details(updated_shift, employee_id, shift_id)

                sent_msg = await update.message.reply_text(
                    shift_details,
                    reply_markup=main_menu_button()
                )
                # Save keyboard message ID
                context.user_data["last_keyboard_message_id"] = sent_msg.message_id
            else:
                await update.message.reply_text(
                    f"✅ Total sales updated to: ${amount:.2f}"
                )
            logger.info(
                f"[UPDATED] Shift {shift_id} Total sales updated to {amount} "
                f"by user {update.effective_user.id}"
            )

            # Check and notify rank changes after updating Total sales
            user_id = context.user_data.get("employee_id")
            if user_id:
                await check_and_notify_rank(user_id, shift_id, context, update.message)
        else:
            logger.warning(f"[EDIT] Failed to update shift {shift_id} - not found")
            await update.message.reply_text(
                "❌ Failed to update shift. It may have been deleted."
            )

        reset_flow(context)
        return START

    except (InvalidOperation, ValueError):
        await update.message.reply_text(
            "❌ Invalid amount. Please enter a positive number (e.g., 350.00):"
        )
        return EDIT_TOTAL_SALES
    except Exception as e:
        logger.error(f"Failed to update Total sales: {e}")
        await update.message.reply_text(
            "❌ Error updating shift.\nPlease try again later."
        )
        return START


# =============================================================================
# STATISTICS AND RANKS HANDLERS
# =============================================================================


async def show_statistics(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Show user statistics (rank, sales, pay day).

    Args:
        update: Telegram update.
        context: Bot context.

    Returns:
        Start state.
    """
    query = update.callback_query
    await query.answer()
    await remove_keyboard(query)

    user = update.effective_user

    try:
        logger.info(f"[STATS] User {user.id} viewing statistics")

        # Show typing indicator
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

        sheets = sheets_service
        rank_service = RankService(sheets)

        # Get current month/year
        now = now_et()
        year = now.year
        month = now.month

        # Get current rank
        rank_record = sheets.get_employee_rank(user.id, year, month)
        if rank_record:
            current_rank = rank_record.get("Current Rank", "Rookie")
        else:
            # Determine rank
            current_rank = sheets.determine_rank(user.id, year, month)

        rank_emoji = rank_service._get_rank_emoji(current_rank)

        # Calculate total sales for current month
        from decimal import Decimal
        all_records = sheets.get_all_shifts()

        total_sales_month = Decimal("0")
        for record in all_records:
            if str(record.get("EmployeeId")) == str(user.id):
                record_date = record.get("Date", "")
                if record_date:
                    try:
                        # Convert PostgreSQL format (YYYY-MM-DD) to expected format (YYYY/MM/DD)
                        date_str = str(record_date).replace("-", "/")
                        dt = parse_dt(date_str)
                        if dt.year == year and dt.month == month:
                            sales = record.get("Total sales", 0)
                            if sales:
                                total_sales_month += Decimal(str(sales))
                    except Exception as e:
                        logger.debug(f"Failed to parse date {record_date}: {e}")
                        pass

        # Calculate total made since last pay day
        # Pay days are 1st and 15th of each month
        if now.day < 15:
            # Last pay day was 1st of current month
            pay_day_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            next_pay_day = now.replace(day=15)
        else:
            # Last pay day was 15th of current month
            pay_day_start = now.replace(day=15, hour=0, minute=0, second=0, microsecond=0)
            # Next pay day is 1st of next month
            if month == 12:
                next_pay_day = now.replace(year=year+1, month=1, day=1)
            else:
                next_pay_day = now.replace(month=month+1, day=1)

        total_made_since_payday = Decimal("0")
        for record in all_records:
            if str(record.get("EmployeeId")) == str(user.id):
                record_date = record.get("Date", "")
                if record_date:
                    try:
                        # Convert PostgreSQL format (YYYY-MM-DD) to expected format (YYYY/MM/DD)
                        date_str = str(record_date).replace("-", "/")
                        dt = parse_dt(date_str)
                        if dt >= pay_day_start:
                            made = record.get("Total made", 0)
                            if made:
                                total_made_since_payday += Decimal(str(made))
                    except Exception as e:
                        logger.debug(f"Failed to parse date {record_date}: {e}")
                        pass

        # Format message
        message = f"📊 Your Statistics\n\n"
        message += f"🏆 Rank: {current_rank} {rank_emoji}\n"
        message += f"💰 Total sales this month: ${total_sales_month:.2f}\n"
        message += f"💵 Total made since last pay day: ${total_made_since_payday:.2f}\n"
        message += f"📅 Next pay day: {next_pay_day.strftime('%B %d, %Y')}\n\n"
        message += "Keep it up! 🚀"

        sent_msg = await query.message.reply_text(message, reply_markup=start_menu_keyboard())
        # Save keyboard message ID
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
    """Show information about rank system.

    Args:
        update: Telegram update.
        context: Bot context.

    Returns:
        Start state.
    """
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
        # Save keyboard message ID
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


# =============================================================================
# CALLBACK QUERY HANDLER
# =============================================================================

async def handle_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Main callback query handler for all inline buttons.

    Args:
        update: Telegram update.
        context: Bot context.

    Returns:
        Next state.
    """
    query = update.callback_query
    data = query.data

    # MAIN_MENU button
    if data == "MAIN_MENU":
        await query.answer()
        await remove_keyboard(query)
        reset_flow(context)
        sent_msg = await query.message.reply_text(
            "🏠 Main menu\n\nChoose an action:",
            reply_markup=start_menu_keyboard()
        )
        # Save keyboard message ID
        context.user_data["last_keyboard_message_id"] = sent_msg.message_id
        return START

    # BACK button
    if data == "BACK":
        await query.answer()
        await remove_keyboard(query)

        prev_state = go_back(context)

        if prev_state == START:
            sent_msg = await query.message.reply_text(
                "Returning to start...\n\nChoose an action:",
                reply_markup=start_menu_keyboard()
            )
            context.user_data["last_keyboard_message_id"] = sent_msg.message_id
            return START

        elif prev_state == CHOOSE_DATE_IN:
            sent_msg = await query.message.reply_text(
                "Choose shift start date:",
                reply_markup=date_choice_keyboard()
            )
            context.user_data["last_keyboard_message_id"] = sent_msg.message_id
            return CHOOSE_DATE_IN

        elif prev_state == CHOOSE_TIME_IN:
            daypart = context.user_data.get("time_daypart_in", "AM")
            sent_msg = await query.message.reply_text(
                "Choose shift start time:",
                reply_markup=time_keyboard("IN", daypart)
            )
            context.user_data["last_keyboard_message_id"] = sent_msg.message_id
            return CHOOSE_TIME_IN

        elif prev_state == CHOOSE_TIME_OUT:
            daypart = context.user_data.get("time_daypart_out", "AM")
            sent_msg = await query.message.reply_text(
                "Choose shift end time:",
                reply_markup=time_keyboard("OUT", daypart)
            )
            context.user_data["last_keyboard_message_id"] = sent_msg.message_id
            return CHOOSE_TIME_OUT

        elif prev_state == PICK_PRODUCT:
            added = context.user_data.get("products", {})
            sent_msg = await query.message.reply_text(
                "Choose product:",
                reply_markup=products_keyboard(exclude=list(added.keys()))
            )
            context.user_data["last_keyboard_message_id"] = sent_msg.message_id
            return PICK_PRODUCT

        elif prev_state == ADD_OR_FINISH:
            sent_msg = await query.message.reply_text(
                "Add more products or finish shift?",
                reply_markup=add_or_finish_keyboard()
            )
            context.user_data["last_keyboard_message_id"] = sent_msg.message_id
            return ADD_OR_FINISH

        else:
            sent_msg = await query.message.reply_text(
                "Returning to start...",
                reply_markup=start_menu_keyboard()
            )
            context.user_data["last_keyboard_message_id"] = sent_msg.message_id
            return START

    # Statistics and Ranks
    if data == "STATISTICS":
        return await show_statistics(update, context)

    if data == "RANKS":
        return await show_ranks_info(update, context)

    # Create shift flow
    if data == "CREATE_SHIFT":
        return await start_create_shift(update, context)

    if data.startswith("DATE_IN:"):
        return await handle_date_choice(update, context)

    if data.startswith("SWITCH:"):
        _, kind, daypart = data.split(":")
        return await handle_time_switch(update, context, kind, daypart)

    if data.startswith("TIME:"):
        _, kind, label = data.split(":", 2)
        label = label.replace("_", " ")

        if kind == "IN":
            return await handle_time_choice_in(update, context, label)
        else:
            return await handle_time_choice_out(update, context, label)

    if data.startswith("PROD:"):
        product = data.split(":", 1)[1]
        return await handle_product_choice(update, context, product)

    if data == "ADD_MODEL":
        return await handle_add_model(update, context)

    if data == "FINISH":
        return await handle_finish_shift(update, context)

    # Edit shift flow
    if data == "EDIT_SHIFT":
        return await start_edit_shift(update, context)

    if data.startswith("EDIT_PICK:"):
        shift_id = int(data.split(":")[1])
        return await handle_edit_pick_shift(update, context, shift_id)

    if data.startswith("EDIT_FIELD:"):
        field = data.split(":")[1]
        return await handle_edit_field_choice(update, context, field)

    if data.startswith("EDIT_DATE_IN:"):
        return await handle_edit_date_choice(update, context)

    if data.startswith("EDIT_SWITCH:"):
        _, kind, daypart = data.split(":")
        # Handle AM/PM switch in edit mode
        if kind == "IN":
            context.user_data["time_daypart_in"] = daypart
            await query.edit_message_reply_markup(reply_markup=time_keyboard("IN", daypart, mode="edit"))
            return EDIT_TIME_IN
        else:
            context.user_data["time_daypart_out"] = daypart
            await query.edit_message_reply_markup(reply_markup=time_keyboard("OUT", daypart, mode="edit"))
            return EDIT_TIME_OUT

    if data.startswith("EDIT_TIME:"):
        _, kind, label = data.split(":", 2)
        label = label.replace("_", " ")

        if kind == "IN":
            return await handle_edit_time_in(update, context, label)
        else:
            return await handle_edit_time_out(update, context, label)

    # Fallback
    await query.answer()
    return ConversationHandler.END


async def handle_unexpected_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle unexpected text messages when user should use buttons.

    Args:
        update: Telegram update.
        context: Bot context.

    Returns:
        Current state.
    """
    user = update.effective_user
    logger.info(f"[TEXT] User {user.id} sent unexpected text: {update.message.text[:50]}")

    # Remove previous inline keyboard
    await remove_last_keyboard(context)

    sent_msg = await update.message.reply_text(
        "Sorry warrior, I think you confused this with the infloww chats... "
        "You don't need to build rapport with me, I am not a fan.\n\n"
        "Just choose an option from the menu!",
        reply_markup=start_menu_keyboard()
    )

    # Save new keyboard message ID
    context.user_data["last_keyboard_message_id"] = sent_msg.message_id
    context.user_data["chat_id"] = update.effective_chat.id

    return START


# =============================================================================
# ADMIN COMMANDS
# =============================================================================

async def recalc_ranks_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Recalculate ranks for all employees (admin only).

    Args:
        update: Telegram update.
        context: Bot context.
    """
    user = update.effective_user

    if user.id not in ADMIN_IDS:
        await update.message.reply_text("⛔ Access denied. Admin only.")
        return

    await update.message.reply_text("🔄 Recalculating ranks...")

    sheets = sheets_service
    now = now_et()
    year, month = now.year, now.month

    try:
        # Get all unique employee IDs from shifts AND employee_ranks this month
        # This ensures we recalculate even for employees whose shifts were deleted
        conn = sheets._get_conn()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT DISTINCT employee_id FROM (
                SELECT employee_id FROM shifts
                WHERE EXTRACT(YEAR FROM date) = %s AND EXTRACT(MONTH FROM date) = %s
                UNION
                SELECT employee_id FROM employee_ranks
                WHERE year = %s AND month = %s
            ) combined
        """, (year, month, year, month))

        employee_ids = [row['employee_id'] for row in cursor.fetchall()]
        cursor.close()
        conn.close()

        updated = 0
        rank_changes = []  # Track rank changes for report

        for emp_id in employee_ids:
            rank_service = RankService(sheets)
            rank_change = rank_service.check_and_update_rank(emp_id, year, month)
            updated += 1

            # If rank changed and there's a bonus
            if rank_change and rank_change.get("changed"):
                bonus = rank_change.get("bonus")
                if bonus:
                    # Apply bonus (will be used on next shift)
                    rank_service.apply_rank_bonus(emp_id, bonus)

                # Track for report
                rank_changes.append({
                    "employee_id": emp_id,
                    "old_rank": rank_change.get("old_rank"),
                    "new_rank": rank_change.get("new_rank"),
                    "rank_up": rank_change.get("rank_up"),
                    "bonus": bonus
                })

        # Build report message
        report = f"✅ Ranks recalculated for {updated} employees\n\n"

        if rank_changes:
            report += "📊 Rank changes:\n"
            for change in rank_changes:
                direction = "⬆️" if change["rank_up"] else "⬇️"
                bonus_text = f" | Bonus: {change['bonus']}" if change["bonus"] else ""
                report += f"{direction} {change['employee_id']}: {change['old_rank']} → {change['new_rank']}{bonus_text}\n"
        else:
            report += "No rank changes detected."

        await update.message.reply_text(report)
        logger.info(f"[ADMIN] User {user.id} recalculated ranks: {len(rank_changes)} changes")

    except Exception as e:
        logger.error(f"[ADMIN] Failed to recalculate ranks: {e}", exc_info=True)
        await update.message.reply_text(f"❌ Error: {e}")
