"""Telegram Shift Tracking Bot - Main entry point."""

import logging
from logging.handlers import RotatingFileHandler
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
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
)
from services.singleton import sheets_service


# Setup logging to file and console
def setup_logging():
    """Configure logging to file and console with rotation."""
    # Create formatter
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # Root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)

    # Clear existing handlers to avoid duplicates
    root_logger.handlers.clear()

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)

    # File handler with rotation (10MB, keep 5 backups)
    file_handler = RotatingFileHandler(
        "logs/bot.log",
        maxBytes=10 * 1024 * 1024,  # 10 MB
        backupCount=5,
        encoding="utf-8"
    )
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(formatter)

    # Add handlers
    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)


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
        return

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

    # Log startup
    logger.info("Bot started - polling for updates...")
    logger.info(f"Products from DB: {', '.join(sheets_service.get_products())}")
    logger.info(f"Commission rate: {Config.COMMISSION_RATE * 100}%")
    logger.info(f"Payout rate: {Config.PAYOUT_RATE * 100}%")

    # Run bot
    application.run_polling()


if __name__ == "__main__":
    main()
