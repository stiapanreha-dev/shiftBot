"""Main handlers for Telegram bot shift tracking.

This module contains the main handler functions. Utility functions
have been moved to src.handlers.navigation and src.handlers.utils.
"""

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
from services.singleton import sheets_service
from services.rank_service import RankService
from services.calculators import CommissionCalculator
from services.formatters import DateFormatter
from src.keyboards import (
    date_choice_keyboard, date_choice_edit_keyboard, time_keyboard,
    products_keyboard, add_or_finish_keyboard, start_menu_keyboard,
    edit_fields_keyboard, shifts_list_keyboard, claim_rank_button
)

# Import utilities from new modules
from src.handlers.navigation import (
    push_state, go_back, reset_flow,
    remove_keyboard, remove_last_keyboard
)
from src.handlers.utils import (
    parse_amount, get_commission_breakdown,
    format_shift_totals, format_shift_details, build_summary
)

logger = logging.getLogger(__name__)

# Admin user IDs for privileged commands
ADMIN_IDS = [7867347055, 2125295046, 8152358885, 7367062056]


# =============================================================================
# HANDLERS
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
                # Parse date using DateFormatter for consistent handling
                parsed_date = DateFormatter.parse_date(str(shift_date_str))
                year = parsed_date.year
                month = parsed_date.month
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

        # Send tomorrow's target notification
        try:
            shift_date = shift_data['date']
            tomorrow_target = sheets.calculate_tomorrow_target(user.id, shift_date)
            bonus_count = sheets.get_fortnight_bonus_count(user.id)

            target_msg = (
                f"\n🎯 Your target for tomorrow is: ${tomorrow_target:,.0f}\n\n"
                f"Hit it and you earn +1% salary boost! Keep grinding 💪\n\n"
                f"Current bonus: +{bonus_count}% ✨"
            )
            await query.message.reply_text(target_msg)
        except Exception as e:
            logger.warning(f"Failed to send target notification: {e}")

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

        # Determine current fortnight and pay day
        # Pay days are 16th (for fortnight 1) and 1st of next month (for fortnight 2)
        if now.day <= 15:
            current_fortnight = 1
            next_pay_day = now.replace(day=16)
        else:
            current_fortnight = 2
            # Next pay day is 1st of next month
            if month == 12:
                next_pay_day = now.replace(year=year+1, month=1, day=1)
            else:
                next_pay_day = now.replace(month=month+1, day=1)

        # Get fortnight data for bonus calculation
        fortnight_data = None
        bonus_count = 0
        bonus_amount = Decimal("0")
        total_salary = Decimal("0")

        try:
            fortnights = sheets.get_employee_fortnights(user.id, year, month)
            for f in fortnights:
                if f.get('fortnight') == current_fortnight:
                    fortnight_data = f
                    bonus_count = f.get('bonus_counter_true_count', 0) or 0
                    bonus_amount = Decimal(str(f.get('bonus_amount', 0) or 0))
                    total_salary = Decimal(str(f.get('total_salary', 0) or 0))
                    break
        except Exception as e:
            logger.warning(f"Failed to get fortnight data: {e}")

        # Calculate total made since last pay day (from shifts in current fortnight)
        total_made_since_payday = Decimal("0")
        if current_fortnight == 1:
            start_day = 1
            end_day = 15
        else:
            start_day = 16
            end_day = 31

        for record in all_records:
            if str(record.get("EmployeeId")) == str(user.id):
                record_date = record.get("Date", "")
                if record_date:
                    try:
                        date_str = str(record_date).replace("-", "/")
                        dt = parse_dt(date_str)
                        if dt.year == year and dt.month == month and start_day <= dt.day <= end_day:
                            made = record.get("Total made", 0)
                            if made:
                                total_made_since_payday += Decimal(str(made))
                    except Exception as e:
                        logger.debug(f"Failed to parse date {record_date}: {e}")

        # Total with bonus
        total_with_bonus = total_made_since_payday + bonus_amount

        # Format message
        message = f"📊 Your Statistics\n\n"
        message += f"🏆 Rank: {current_rank} {rank_emoji}\n"
        message += f"💰 Total sales this month: ${total_sales_month:.2f}\n"
        message += f"💵 Total made since last pay day: ${total_with_bonus:.2f}\n"
        message += f"✨ Current applied bonus: +{bonus_count}% (${bonus_amount:.2f})\n"
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
