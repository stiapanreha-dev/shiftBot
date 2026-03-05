"""Shift creation handlers."""

import logging
from decimal import Decimal, InvalidOperation

from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler

from config import (
    Config, START, CHOOSE_DATE_IN, CHOOSE_TIME_IN, CHOOSE_TIME_OUT,
    PICK_PRODUCT, ENTER_AMOUNT, ADD_OR_FINISH
)
from src.time_utils import (
    now_et, format_dt, hour_from_label, create_datetime_from_date_and_hour,
    get_server_date
)
from services.singleton import sheets_service
from services.rank_service import RankService
from services.formatters import DateFormatter
from src.keyboards import (
    date_choice_keyboard, time_keyboard, products_keyboard,
    add_or_finish_keyboard, start_menu_keyboard, claim_rank_button
)
from src.handlers.navigation import push_state, reset_flow, remove_keyboard
from src.handlers.utils import parse_amount, build_summary

logger = logging.getLogger(__name__)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle /start command."""
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
    context.user_data["last_keyboard_message_id"] = sent_msg.message_id

    return START


async def start_create_shift(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start shift creation flow."""
    query = update.callback_query
    await query.answer()
    await remove_keyboard(query)

    user = update.effective_user
    logger.info(f"[CREATE] User {user.id} started shift creation")

    if "products" not in context.user_data:
        context.user_data["products"] = {}

    push_state(context, CHOOSE_DATE_IN)

    sent_msg = await query.message.reply_text(
        "Choose shift start date:",
        reply_markup=date_choice_keyboard()
    )
    context.user_data["last_keyboard_message_id"] = sent_msg.message_id

    return CHOOSE_DATE_IN


async def handle_date_choice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle date choice for Clock in."""
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
    context.user_data["last_keyboard_message_id"] = sent_msg.message_id

    return CHOOSE_TIME_IN


async def handle_time_switch(update: Update, context: ContextTypes.DEFAULT_TYPE, kind: str, daypart: str) -> int:
    """Handle AM/PM switch."""
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
    """Handle time choice for Clock in."""
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

    clock_out_date, _ = get_server_date(0)
    context.user_data["clock_out_date"] = clock_out_date
    context.user_data["time_daypart_out"] = "AM"

    push_state(context, CHOOSE_TIME_OUT)

    sent_msg = await query.message.reply_text(
        "Choose shift end time:",
        reply_markup=time_keyboard("OUT", "AM")
    )
    context.user_data["last_keyboard_message_id"] = sent_msg.message_id

    return CHOOSE_TIME_OUT


async def handle_time_choice_out(update: Update, context: ContextTypes.DEFAULT_TYPE, label: str) -> int:
    """Handle time choice for Clock out."""
    query = update.callback_query
    await query.answer()
    await remove_keyboard(query)

    hour = hour_from_label(label)
    date = context.user_data["clock_out_date"]
    dt = create_datetime_from_date_and_hour(date, hour)

    context.user_data["clock_out"] = format_dt(dt)
    context.user_data["clock_out_dt"] = dt

    user = update.effective_user

    clock_in_dt = context.user_data.get("clock_in_dt")
    if dt <= clock_in_dt:
        logger.warning(f"[TIME_OUT] User {user.id} selected Clock out before Clock in: {format_dt(dt)}")
        sent_msg = await query.message.reply_text(
            "⚠️ Error: End time must be after start time!\n"
            "Please choose a later time.",
            reply_markup=time_keyboard("OUT", context.user_data["time_daypart_out"])
        )
        context.user_data["last_keyboard_message_id"] = sent_msg.message_id
        return CHOOSE_TIME_OUT

    logger.info(f"[TIME_OUT] User {user.id} selected Clock out: {format_dt(dt)}")

    push_state(context, PICK_PRODUCT)

    sent_msg = await query.message.reply_text(
        "Choose product:",
        reply_markup=products_keyboard()
    )
    context.user_data["last_keyboard_message_id"] = sent_msg.message_id

    return PICK_PRODUCT


async def handle_product_choice(update: Update, context: ContextTypes.DEFAULT_TYPE, product: str) -> int:
    """Handle product selection."""
    query = update.callback_query
    await query.answer()
    await remove_keyboard(query)

    user = update.effective_user

    if product in context.user_data.get("products", {}):
        logger.warning(f"[PRODUCT] User {user.id} tried to add duplicate product: {product}")
        await query.answer("⚠️ This product already added!", show_alert=True)
        sent_msg = await query.message.reply_text(
            f"Product '{product}' already added.\nChoose another product:",
            reply_markup=products_keyboard(exclude=list(context.user_data["products"].keys()))
        )
        context.user_data["last_keyboard_message_id"] = sent_msg.message_id
        return PICK_PRODUCT

    logger.info(f"[PRODUCT] User {user.id} selected product: {product}")
    context.user_data["current_product"] = product

    await query.message.reply_text(
        f"Enter sales amount for '{product}':\n(e.g., 99.90)"
    )

    return ENTER_AMOUNT


async def handle_amount_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle amount input."""
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

    if "products" not in context.user_data:
        context.user_data["products"] = {}

    context.user_data["products"][product] = amount

    logger.info(f"[AMOUNT] User {user.id} entered amount for {product}: {amount}")

    push_state(context, ADD_OR_FINISH)

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
    context.user_data["last_keyboard_message_id"] = sent_msg.message_id

    return ADD_OR_FINISH


async def handle_add_model(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle Add model button."""
    query = update.callback_query
    await query.answer()
    await remove_keyboard(query)

    push_state(context, PICK_PRODUCT)

    added = context.user_data.get("products", {})
    message = "Already added:\n"

    for product, amount in added.items():
        message += f"• {product}: {amount:.2f}\n"

    message += "\nChoose next product:"

    sent_msg = await query.message.reply_text(
        message,
        reply_markup=products_keyboard(exclude=list(added.keys()))
    )
    context.user_data["last_keyboard_message_id"] = sent_msg.message_id

    return PICK_PRODUCT


async def check_and_notify_rank(
    user_id: int,
    shift_id: int,
    context: ContextTypes.DEFAULT_TYPE,
    message
) -> None:
    """Check for rank changes and send notification."""
    try:
        sheets = sheets_service
        rank_service = RankService(sheets)

        shift = sheets.get_shift_by_id(shift_id)
        if shift:
            shift_date_str = shift.get('date') or shift.get('shift_date') or shift.get('Date')
            if shift_date_str:
                parsed_date = DateFormatter.parse_date(str(shift_date_str))
                year = parsed_date.year
                month = parsed_date.month
            else:
                now = now_et()
                year = now.year
                month = now.month
        else:
            now = now_et()
            year = now.year
            month = now.month

        rank_change = rank_service.check_and_update_rank(user_id, year, month)

        if rank_change and rank_change.get("changed"):
            notification = rank_service.format_rank_notification(rank_change)
            sent_msg = await message.reply_text(
                notification,
                reply_markup=claim_rank_button()
            )
            context.user_data["last_keyboard_message_id"] = sent_msg.message_id

            hush_reward = rank_change.get("hush_reward")
            if hush_reward and hush_reward > 0:
                new_rank = rank_change.get("new_rank", "")
                rank_service.apply_hush_reward(user_id, new_rank, hush_reward)

            sheets.mark_rank_notified(user_id, year, month)

            logger.info(
                f"[RANK] User {user_id} rank changed: "
                f"{rank_change.get('old_rank')} → {rank_change.get('new_rank')}"
            )

    except Exception as e:
        logger.error(f"[ERROR] Failed to check rank for user {user_id}: {e}", exc_info=True)


async def handle_finish_shift(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle Finish shift button - save shift to database."""
    query = update.callback_query
    await query.answer()
    await remove_keyboard(query)

    user = update.effective_user
    shift_id = None

    logger.info(f"[SAVE] User {user.id} finishing shift creation")

    try:
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    except Exception:
        pass

    sheets = sheets_service

    shift_data = {
        "date": format_dt(now_et()),
        "employee_id": context.user_data["employee_id"],
        "employee_name": context.user_data["employee_name"],
        "clock_in": context.user_data["clock_in"],
        "clock_out": context.user_data["clock_out"],
        "products": context.user_data["products"],
    }

    total_sales = sum(Decimal(str(v)) for v in shift_data["products"].values())
    products_str = ", ".join([f"{k}:{v}" for k, v in shift_data["products"].items()])

    try:
        shift_id = sheets.create_shift(shift_data)
        created_shift = sheets.get_shift_by_id(shift_id)
        logger.info(
            f"[SAVED] Shift {shift_id} created for user {user.id} | "
            f"Clock in: {shift_data['clock_in']} | "
            f"Clock out: {shift_data['clock_out']} | "
            f"Products: {products_str} | "
            f"Total: {total_sales}"
        )
    except Exception as e:
        logger.error(f"[DB_ERROR] Failed to save shift for user {user.id}: {e}", exc_info=True)
        try:
            await query.message.reply_text(
                "❌ Error creating shift.\n"
                "Please try again. If the problem persists, contact administrator."
            )
        except Exception:
            pass
        reset_flow(context)
        return ConversationHandler.END

    try:
        summary = build_summary(shift_data, shift_id, created_shift)
        from src.keyboards import main_menu_button
        sent_msg = await query.message.reply_text(summary, reply_markup=main_menu_button())
        context.user_data["last_keyboard_message_id"] = sent_msg.message_id
    except Exception as e:
        logger.warning(f"[TG_ERROR] Failed to send summary for shift {shift_id}, user {user.id}: {e}")
        try:
            await query.message.reply_text(
                f"✅ Shift #{shift_id} saved successfully!\n"
                "⚠️ There was an issue displaying the summary."
            )
        except Exception:
            pass

    try:
        shift_date = shift_data['date']
        tomorrow_target = sheets.calculate_tomorrow_target(user.id, shift_date)
        bonus_count = sheets.get_fortnight_bonus_count(user.id)

        target_msg = (
            f"\n🎯 Your target for tomorrow is: ${tomorrow_target:,.0f}\n\n"
            f"Hit it and you earn +1% salary boost! Keep grinding 💪\n\n"
            f"Current bonus: +{bonus_count}% ✨"
        )
        sent_msg = await query.message.reply_text(target_msg)

        try:
            await context.bot.pin_chat_message(
                chat_id=query.message.chat_id,
                message_id=sent_msg.message_id,
                disable_notification=True
            )
        except Exception as pin_error:
            logger.debug(f"Could not pin target message: {pin_error}")
    except Exception as e:
        logger.warning(f"[TG_ERROR] Failed to send target notification: {e}")

    try:
        await check_and_notify_rank(user.id, shift_id, context, query.message)
    except Exception as e:
        logger.warning(f"[RANK_ERROR] Failed to check rank for user {user.id}: {e}")

    reset_flow(context)
    return START
