"""Configuration module for Telegram Shift Tracking Bot."""

import os
from typing import List
from dotenv import load_dotenv

load_dotenv()


class Config:
    """Bot configuration loaded from environment variables."""

    # Telegram Bot
    BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")

    # Google Sheets
    GOOGLE_SA_JSON: str = os.getenv("GOOGLE_SA_JSON", "google_sheets_credentials.json")
    SPREADSHEET_ID: str = os.getenv("SPREADSHEET_ID", "")
    SHEET_NAME: str = os.getenv("SHEET_NAME", "Shifts")

    # Products
    PRODUCTS: List[str] = [
        p.strip()
        for p in os.getenv("PRODUCTS", "").split(",")
        if p.strip()
    ]

    # Rates
    COMMISSION_RATE: float = float(os.getenv("COMMISSION_RATE", "0.20"))
    PAYOUT_RATE: float = float(os.getenv("PAYOUT_RATE", "1.00"))

    # Time
    USE_FIXED_UTC_MINUS_5: bool = os.getenv("USE_FIXED_UTC_MINUS_5", "false").lower() == "true"
    DATE_FORMAT: str = "%Y/%m/%d %H:%M:%S"

    @classmethod
    def validate(cls) -> None:
        """Validate required configuration parameters.

        Raises:
            ValueError: If any required parameter is missing.
        """
        required = {
            "BOT_TOKEN": cls.BOT_TOKEN,
            "SPREADSHEET_ID": cls.SPREADSHEET_ID,
        }

        missing = [name for name, value in required.items() if not value]

        if missing:
            raise ValueError(f"Missing required environment variables: {', '.join(missing)}")

        if not cls.PRODUCTS:
            raise ValueError("PRODUCTS must contain at least one product")

        if not os.path.exists(cls.GOOGLE_SA_JSON):
            raise ValueError(f"Google credentials file not found: {cls.GOOGLE_SA_JSON}")


# FSM States
(
    START,
    CHOOSE_DATE_IN,
    CHOOSE_TIME_IN,
    CHOOSE_TIME_OUT,
    PICK_PRODUCT,
    ENTER_AMOUNT,
    ADD_OR_FINISH,
    EDIT_MENU,
    EDIT_PICK_SHIFT,
    EDIT_FIELD,
    EDIT_DATE_IN,
    EDIT_TIME_IN,
    EDIT_DATE_OUT,
    EDIT_TIME_OUT,
    EDIT_TOTAL_SALES,
) = range(15)
