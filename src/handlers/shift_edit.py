"""Shift editing handlers."""

import logging
from decimal import Decimal, InvalidOperation
from datetime import timedelta

from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler

from config import (
    Config,
    START, EDIT_PICK_SHIFT, EDIT_FIELD,
    EDIT_DATE_IN, EDIT_TIME_IN, EDIT_TIME_OUT, EDIT_TOTAL_SALES
)
from src.time_utils import (
    hour_from_label, create_datetime_from_date_and_hour, format_dt, parse_dt
)
from services.singleton import sheets_service
from src.keyboards import (
    date_choice_edit_keyboard, time_keyboard,
    edit_fields_keyboard, shifts_list_keyboard
)
from src.handlers.navigation import push_state, reset_flow, remove_keyboard
from src.handlers.utils import parse_amount, format_shift_details
from src.handlers.shift_create import check_and_notify_rank

logger = logging.getLogger(__name__)


async def start_edit_shift(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start shift editing flow - show last 3 shifts."""
    query = update.callback_query
    await query.answer()
    await remove_keyboard(query)

    user = update.effective_user

    try:
        logger.info(f"[EDIT] User {user.id} started shift editing")
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
        context.user_data["last_keyboard_message_id"] = sent_msg.message_id

        return EDIT_PICK_SHIFT

    except Exception as e:
        logger.error(f"[ERROR] Failed to get shifts for editing for user {user.id}: {e}", exc_info=True)
        await query.message.reply_text(
            "❌ Error loading shifts.\nPlease try again later."
        )
        return ConversationHandler.END


async def handle_edit_pick_shift(update: Update, context: ContextTypes.DEFAULT_TYPE, shift_id: int) -> int:
    """Handle shift selection for editing."""
    query = update.callback_query
    await query.answer()
    await remove_keyboard(query)

    try:
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

        sheets = sheets_service
        shift = sheets.get_shift_by_id(shift_id)

        if not shift:
            await query.message.reply_text(
                "❌ Shift not found. It may have been deleted."
            )
            return ConversationHandler.END

        # shift_id comes from callback data, which a client can forge:
        # only the shift owner (or an admin) may edit it
        user = update.effective_user
        if shift.get("employee_id") != user.id and user.id not in Config.ADMIN_IDS:
            logger.warning(
                f"[EDIT] User {user.id} tried to edit foreign shift {shift_id}"
            )
            await query.message.reply_text("❌ You can only edit your own shifts.")
            return ConversationHandler.END

        context.user_data["edit_shift_id"] = shift_id
        context.user_data["edit_shift_data"] = shift

        push_state(context, EDIT_FIELD)

        sent_msg = await query.message.reply_text(
            f"Editing shift ID {shift_id}\n\nSelect field to edit:",
            reply_markup=edit_fields_keyboard()
        )
        context.user_data["last_keyboard_message_id"] = sent_msg.message_id

        return EDIT_FIELD

    except Exception as e:
        logger.error(f"Failed to load shift {shift_id}: {e}")
        await query.message.reply_text(
            "❌ Error loading shift.\nPlease try again later."
        )
        return ConversationHandler.END


async def handle_edit_field_choice(update: Update, context: ContextTypes.DEFAULT_TYPE, field: str) -> int:
    """Handle field choice for editing."""
    query = update.callback_query
    await query.answer()
    await remove_keyboard(query)

    context.user_data["edit_field"] = field
    shift_data = context.user_data["edit_shift_data"]

    if field == "IN":
        record_date_str = shift_data.get("Date", "")
        record_date_str = str(record_date_str).replace("-", "/")
        record_date = parse_dt(record_date_str).date()
        context.user_data["edit_record_date"] = record_date

        push_state(context, EDIT_DATE_IN)

        sent_msg = await query.message.reply_text(
            f"Record date: {record_date_str}\n\nChoose date for Clock in:",
            reply_markup=date_choice_edit_keyboard()
        )
        context.user_data["last_keyboard_message_id"] = sent_msg.message_id

        return EDIT_DATE_IN

    elif field == "OUT":
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
    """Handle date choice when editing Clock in."""
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
    context.user_data["last_keyboard_message_id"] = sent_msg.message_id

    return EDIT_TIME_IN


async def handle_edit_time_in(update: Update, context: ContextTypes.DEFAULT_TYPE, label: str) -> int:
    """Handle time choice when editing Clock in."""
    query = update.callback_query
    await query.answer()

    try:
        hour = hour_from_label(label)
        date = context.user_data["clock_in_date"]
        dt = create_datetime_from_date_and_hour(date, hour)
        clock_in_str = format_dt(dt)

        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

        sheets = sheets_service
        shift_id = context.user_data["edit_shift_id"]

        success = sheets.update_shift_field(shift_id, "Clock in", clock_in_str)

        if success:
            sheets.recalculate_worked_hours(shift_id)

            # Salary aggregates depend on worked hours and the shift's date:
            # recalc the new fortnight, and the old one if the date changed
            try:
                old_date_str = str(context.user_data.get("edit_shift_data", {}).get("Date", ""))
                new_date = dt.date()
                shift_emp_id = context.user_data["edit_shift_data"]["employee_id"]
                sheets.update_fortnight_totals_for_date(shift_emp_id, new_date)
                if old_date_str:
                    old_date = parse_dt(old_date_str.replace("-", "/")).date()
                    if old_date != new_date:
                        sheets.update_fortnight_totals_for_date(shift_emp_id, old_date)
            except Exception as e:
                logger.warning(f"Failed to update fortnight totals after Clock in edit: {e}")

            from src.keyboards import main_menu_button

            updated_shift = sheets.get_shift_by_id(shift_id)

            if updated_shift:
                employee_id = context.user_data.get("employee_id")
                shift_details = format_shift_details(updated_shift, employee_id, shift_id)

                sent_msg = await query.message.reply_text(
                    shift_details,
                    reply_markup=main_menu_button()
                )
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
    """Handle time choice when editing Clock out."""
    query = update.callback_query
    await query.answer()

    try:
        hour = hour_from_label(label)
        date = context.user_data["clock_out_date"]
        dt = create_datetime_from_date_and_hour(date, hour)
        clock_out_str = format_dt(dt)

        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

        sheets = sheets_service
        shift_id = context.user_data["edit_shift_id"]

        success = sheets.update_shift_field(shift_id, "Clock out", clock_out_str)

        if success:
            sheets.recalculate_worked_hours(shift_id)

            # Worked hours changed — the fortnight salary must follow
            try:
                shift_data = context.user_data["edit_shift_data"]
                shift_date = parse_dt(str(shift_data["Date"]).replace("-", "/")).date()
                sheets.update_fortnight_totals_for_date(shift_data["employee_id"], shift_date)
            except Exception as e:
                logger.warning(f"Failed to update fortnight totals after Clock out edit: {e}")

            from src.keyboards import main_menu_button

            updated_shift = sheets.get_shift_by_id(shift_id)

            if updated_shift:
                employee_id = context.user_data.get("employee_id")
                shift_details = format_shift_details(updated_shift, employee_id, shift_id)

                sent_msg = await query.message.reply_text(
                    shift_details,
                    reply_markup=main_menu_button()
                )
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
    """Handle Total sales input when editing."""
    text = update.message.text.strip()

    try:
        amount = parse_amount(text)
        if amount < 0:
            raise ValueError("Negative amount")

        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

        sheets = sheets_service
        shift_id = context.user_data["edit_shift_id"]

        success = sheets.update_total_sales(shift_id, amount)

        if success:
            updated_shift = sheets.get_shift_by_id(shift_id)

            if updated_shift:
                from src.keyboards import main_menu_button

                employee_id = context.user_data.get("employee_id")
                shift_details = format_shift_details(updated_shift, employee_id, shift_id)

                sent_msg = await update.message.reply_text(
                    shift_details,
                    reply_markup=main_menu_button()
                )
                context.user_data["last_keyboard_message_id"] = sent_msg.message_id
            else:
                await update.message.reply_text(
                    f"✅ Total sales updated to: ${amount:.2f}"
                )
            logger.info(
                f"[UPDATED] Shift {shift_id} Total sales updated to {amount} "
                f"by user {update.effective_user.id}"
            )

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
