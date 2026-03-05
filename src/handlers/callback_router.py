"""Callback query routing and unexpected text handler."""

import logging

from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler

from config import (
    START, CHOOSE_DATE_IN, CHOOSE_TIME_IN, CHOOSE_TIME_OUT,
    PICK_PRODUCT, ADD_OR_FINISH,
    EDIT_TIME_IN, EDIT_TIME_OUT
)
from src.keyboards import (
    date_choice_keyboard, time_keyboard, products_keyboard,
    add_or_finish_keyboard, start_menu_keyboard
)
from src.handlers.navigation import (
    go_back, reset_flow, remove_keyboard, remove_last_keyboard
)
from src.handlers.shift_create import (
    start_create_shift, handle_date_choice, handle_time_switch,
    handle_time_choice_in, handle_time_choice_out,
    handle_product_choice, handle_add_model, handle_finish_shift
)
from src.handlers.shift_edit import (
    start_edit_shift, handle_edit_pick_shift,
    handle_edit_field_choice, handle_edit_date_choice,
    handle_edit_time_in, handle_edit_time_out
)
from src.handlers.stats import show_statistics, show_ranks_info, show_hush_balance

logger = logging.getLogger(__name__)


async def handle_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Main callback query handler for all inline buttons."""
    query = update.callback_query
    data = query.data

    try:
        return await _dispatch_callback(update, context, query, data)
    except (ValueError, IndexError) as e:
        logger.error(f"Invalid callback data '{data}': {e}")
        await query.answer("Invalid action, please try again.")
        return ConversationHandler.END


async def _dispatch_callback(update, context, query, data) -> int:
    """Dispatch callback query to appropriate handler."""
    # MAIN_MENU button
    if data == "MAIN_MENU":
        await query.answer()
        await remove_keyboard(query)
        reset_flow(context)
        sent_msg = await query.message.reply_text(
            "🏠 Main menu\n\nChoose an action:",
            reply_markup=start_menu_keyboard()
        )
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

    # Statistics, Ranks and HUSH Balance
    if data == "STATISTICS":
        return await show_statistics(update, context)

    if data == "RANKS":
        return await show_ranks_info(update, context)

    if data == "HUSH_BALANCE":
        return await show_hush_balance(update, context)

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
    """Handle unexpected text messages when user should use buttons."""
    user = update.effective_user
    logger.info(f"[TEXT] User {user.id} sent unexpected text: {update.message.text[:50]}")

    await remove_last_keyboard(context)

    sent_msg = await update.message.reply_text(
        "Sorry warrior, I think you confused this with the infloww chats... "
        "You don't need to build rapport with me, I am not a fan.\n\n"
        "Just choose an option from the menu!",
        reply_markup=start_menu_keyboard()
    )

    context.user_data["last_keyboard_message_id"] = sent_msg.message_id
    context.user_data["chat_id"] = update.effective_chat.id

    return START
