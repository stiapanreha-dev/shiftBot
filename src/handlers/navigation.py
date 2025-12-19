"""Navigation utilities for state management."""

import logging
from telegram.ext import ContextTypes

from config import START

logger = logging.getLogger(__name__)


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
            context.user_data.pop("last_keyboard_message_id", None)


async def send_keyboard_message(
    query,
    context: ContextTypes.DEFAULT_TYPE,
    text: str,
    keyboard
) -> None:
    """Send message with keyboard and save message ID.

    This helper reduces the repetitive pattern of sending a keyboard
    and saving the message ID.

    Args:
        query: CallbackQuery object
        context: Bot context
        text: Message text
        keyboard: InlineKeyboardMarkup
    """
    sent_msg = await query.message.reply_text(text, reply_markup=keyboard)
    context.user_data["last_keyboard_message_id"] = sent_msg.message_id
