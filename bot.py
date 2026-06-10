"""Telegram Shift Tracking Bot - Main entry point."""

import html
import logging
import sys
import traceback
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    ConversationHandler,
    filters,
)

from config import Config, START, CHOOSE_DATE_IN, CHOOSE_TIME_IN, CHOOSE_TIME_OUT
from config import PICK_PRODUCT, ENTER_AMOUNT, ADD_OR_FINISH
from config import EDIT_MENU, EDIT_PICK_SHIFT, EDIT_FIELD
from config import EDIT_DATE_IN, EDIT_TIME_IN, EDIT_DATE_OUT, EDIT_TIME_OUT, EDIT_TOTAL_SALES

from src.handlers import (
    start,
    handle_amount_input,
    handle_edit_total_sales_input,
    handle_callback_query,
    handle_unexpected_text,
    recalc_ranks_command,
    withdraw_hush_command,
)
from services.singleton import sheets_service


# Setup logging
def setup_logging():
    """Configure logging to stdout only.

    systemd redirects stdout to logs/bot.log (StandardOutput=append:),
    logrotate rotates the file. Writing to the file from here as well
    would duplicate every line.
    """
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    root_logger.handlers.clear()

    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # httpx logs every getUpdates poll (every 10s) at INFO
    logging.getLogger("httpx").setLevel(logging.WARNING)


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log unhandled handler exceptions, answer the user, alert the admin."""
    logger = logging.getLogger(__name__)
    logger.error("Unhandled exception while processing update", exc_info=context.error)

    if isinstance(update, Update) and update.effective_message:
        try:
            await update.effective_message.reply_text(
                "⚠️ Something went wrong. Please try again or send /start."
            )
        except Exception:
            pass

    if Config.ADMIN_IDS and context.error is not None:
        tb = "".join(traceback.format_exception(
            type(context.error), context.error, context.error.__traceback__
        ))
        try:
            await context.bot.send_message(
                chat_id=Config.ADMIN_IDS[0],
                text=f"⚠️ Bot error:\n<pre>{html.escape(tb[-1500:])}</pre>",
                parse_mode=ParseMode.HTML,
            )
        except Exception:
            pass


def main() -> None:
    """Run the bot."""
    # Setup logging
    setup_logging()
    logger = logging.getLogger(__name__)

    # Validate configuration
    try:
        Config.validate()
        logger.info("Configuration validated successfully")
    except ValueError as e:
        logger.error(f"Configuration error: {e}")
        sys.exit(1)

    # Create application
    application = Application.builder().token(Config.BOT_TOKEN).build()

    # Define conversation handler
    conversation_handler = ConversationHandler(
        entry_points=[
            CommandHandler("start", start),
        ],
        states={
            START: [
                CallbackQueryHandler(handle_callback_query),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_unexpected_text),
            ],
            CHOOSE_DATE_IN: [
                CallbackQueryHandler(handle_callback_query),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_unexpected_text),
            ],
            CHOOSE_TIME_IN: [
                CallbackQueryHandler(handle_callback_query),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_unexpected_text),
            ],
            CHOOSE_TIME_OUT: [
                CallbackQueryHandler(handle_callback_query),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_unexpected_text),
            ],
            PICK_PRODUCT: [
                CallbackQueryHandler(handle_callback_query),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_unexpected_text),
            ],
            ENTER_AMOUNT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_amount_input),
                CallbackQueryHandler(handle_callback_query),
            ],
            ADD_OR_FINISH: [
                CallbackQueryHandler(handle_callback_query),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_unexpected_text),
            ],
            EDIT_PICK_SHIFT: [
                CallbackQueryHandler(handle_callback_query),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_unexpected_text),
            ],
            EDIT_FIELD: [
                CallbackQueryHandler(handle_callback_query),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_unexpected_text),
            ],
            EDIT_DATE_IN: [
                CallbackQueryHandler(handle_callback_query),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_unexpected_text),
            ],
            EDIT_TIME_IN: [
                CallbackQueryHandler(handle_callback_query),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_unexpected_text),
            ],
            EDIT_TIME_OUT: [
                CallbackQueryHandler(handle_callback_query),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_unexpected_text),
            ],
            EDIT_TOTAL_SALES: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_edit_total_sales_input),
                CallbackQueryHandler(handle_callback_query),
            ],
        },
        fallbacks=[
            CommandHandler("start", start),
            CallbackQueryHandler(handle_callback_query),
        ],
        allow_reentry=True,
    )

    # Add handlers
    application.add_handler(conversation_handler)
    application.add_handler(CommandHandler("recalc_ranks", recalc_ranks_command))
    application.add_handler(CommandHandler("withdraw_hush", withdraw_hush_command))
    application.add_error_handler(error_handler)

    # Log startup
    logger.info("Bot started - polling for updates...")
    logger.info(f"Products from DB: {', '.join(sheets_service.get_products())}")
    logger.info(f"Commission rate: {Config.COMMISSION_RATE * 100}%")
    logger.info(f"Payout rate: {Config.PAYOUT_RATE * 100}%")

    # Run bot
    application.run_polling()


if __name__ == "__main__":
    main()
