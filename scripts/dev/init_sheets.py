"""Script to initialize new Google Sheets for the rank system."""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))
import logging
from typing import List
import gspread
from config import Config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class SheetsInitializer:
    """Initialize new sheets for rank and bonus system."""

    def __init__(self):
        """Initialize Google Sheets client."""
        try:
            self.client = gspread.service_account(filename=Config.GOOGLE_SA_JSON)
            self.spreadsheet = self.client.open_by_key(Config.SPREADSHEET_ID)
            logger.info("Connected to Google Sheets")
        except Exception as e:
            logger.error(f"Failed to connect to Google Sheets: {e}")
            raise

    def get_or_create_worksheet(self, title: str, rows: int = 100, cols: int = 20) -> gspread.Worksheet:
        """Get existing worksheet or create new one.

        Args:
            title: Worksheet title
            rows: Number of rows
            cols: Number of columns

        Returns:
            Worksheet object
        """
        try:
            ws = self.spreadsheet.worksheet(title)
            logger.info(f"Worksheet '{title}' already exists")
            return ws
        except gspread.WorksheetNotFound:
            logger.info(f"Creating worksheet '{title}'...")
            ws = self.spreadsheet.add_worksheet(title=title, rows=rows, cols=cols)
            logger.info(f"Worksheet '{title}' created")
            return ws

    def init_employee_settings(self) -> None:
        """Initialize EmployeeSettings sheet.

        Structure:
        | EmployeeId | Hourly wage | Sales commission |
        """
        ws = self.get_or_create_worksheet("EmployeeSettings", rows=100, cols=10)

        headers = ["EmployeeId", "Hourly wage", "Sales commission"]

        # Check if headers exist
        existing_headers = ws.row_values(1)
        if existing_headers != headers:
            ws.update("A1", [headers], value_input_option="RAW")
            logger.info("EmployeeSettings headers set")

        # Add example data if empty
        if len(ws.get_all_values()) == 1:
            example_data = [
                ["120962578", "15.00", "8.0"],
                ["123456789", "18.00", "10.0"],
            ]
            ws.append_rows(example_data, value_input_option="RAW")
            logger.info("EmployeeSettings example data added")

    def init_dynamic_rates(self) -> None:
        """Initialize DynamicRates sheet.

        Structure:
        | Min Amount | Max Amount | Percentage |
        """
        ws = self.get_or_create_worksheet("DynamicRates", rows=50, cols=5)

        headers = ["Min Amount", "Max Amount", "Percentage"]

        # Check if headers exist
        existing_headers = ws.row_values(1)
        if existing_headers != headers:
            ws.update("A1", [headers], value_input_option="RAW")
            logger.info("DynamicRates headers set")

        # Add default rates if empty
        if len(ws.get_all_values()) == 1:
            default_rates = [
                ["0", "499.99", "0.0"],
                ["500", "999.99", "2.0"],
                ["1000", "1999.99", "4.0"],
                ["2000", "999999", "6.0"],
            ]
            ws.append_rows(default_rates, value_input_option="RAW")
            logger.info("DynamicRates default data added")

    def init_ranks(self) -> None:
        """Initialize Ranks sheet.

        Structure:
        | Rank Name | Min Amount | Max Amount | Emoji | Bonus 1 | Bonus 2 | Bonus 3 | TEXT |
        """
        ws = self.get_or_create_worksheet("Ranks", rows=50, cols=10)

        headers = ["Rank Name", "Min Amount", "Max Amount", "Emoji", "Bonus 1", "Bonus 2", "Bonus 3", "TEXT"]

        # Check if headers exist
        existing_headers = ws.row_values(1)
        if existing_headers != headers:
            ws.update("A1", [headers], value_input_option="RAW")
            logger.info("Ranks headers set")

        # Add rank data if empty
        if len(ws.get_all_values()) == 1:
            ranks_data = [
                ["Rookie", "0", "1999.99", "🧑‍🚀", "none", "none", "none", "Keep pushing!"],
                ["Hustler", "2000", "3999.99", "💪", "flat_10", "percent_next_1", "percent_prev_1", "You're really killing it!"],
                ["Closer", "4000", "6999.99", "💼", "flat_25", "percent_next_2", "flat_15", "You're really killing it!"],
                ["Shark", "7000", "9999.99", "🦈", "flat_50", "paid_day_off", "percent_next_3", "You're really killing it!"],
                ["King of Greed", "10000", "14999.99", "💀", "flat_100", "percent_all_2", "telegram_premium", "You're really killing it!"],
                ["Chatting God", "15000", "999999", "🔥", "flat_200", "double_commission", "flat_125", "You're really killing it!"],
            ]
            ws.append_rows(ranks_data, value_input_option="RAW")
            logger.info("Ranks data added")

    def init_employee_ranks(self) -> None:
        """Initialize EmployeeRanks sheet.

        Structure:
        | EmployeeId | Current Rank | Previous Rank | Month | Year | Notified | Last Updated |
        """
        ws = self.get_or_create_worksheet("EmployeeRanks", rows=200, cols=10)

        headers = ["EmployeeId", "Current Rank", "Previous Rank", "Month", "Year", "Notified", "Last Updated"]

        # Check if headers exist
        existing_headers = ws.row_values(1)
        if existing_headers != headers:
            ws.update("A1", [headers], value_input_option="RAW")
            logger.info("EmployeeRanks headers set")

    def init_active_bonuses(self) -> None:
        """Initialize ActiveBonuses sheet.

        Structure:
        | ID | EmployeeId | Bonus Type | Value | Applied | Shift ID | Created At |
        """
        ws = self.get_or_create_worksheet("ActiveBonuses", rows=500, cols=10)

        headers = ["ID", "EmployeeId", "Bonus Type", "Value", "Applied", "Shift ID", "Created At"]

        # Check if headers exist
        existing_headers = ws.row_values(1)
        if existing_headers != headers:
            ws.update("A1", [headers], value_input_option="RAW")
            logger.info("ActiveBonuses headers set")

    def update_shifts_headers(self) -> None:
        """Update Shifts sheet with new columns.

        New columns after Clock out:
        - Worked hours/shift (after Clock out)

        New columns before Total made:
        - % (after Net sales)
        - Total per hour (after %)
        - Commissions (after Total per hour)
        """
        try:
            ws = self.spreadsheet.worksheet(Config.SHEET_NAME)

            current_headers = ws.row_values(1)
            logger.info(f"Current Shifts headers: {current_headers}")

            # Expected structure:
            # ID, Date, EmployeeId, EmployeeName, Clock in, Clock out,
            # Worked hours/shift, Model A, Model B, Model C, ...,
            # Total sales, Net sales, %, Total per hour, Commissions, Total made

            base_headers = ["ID", "Date", "EmployeeId", "EmployeeName", "Clock in", "Clock out", "Worked hours/shift"]
            tail_headers = ["Total sales", "Net sales", "%", "Total per hour", "Commissions", "Total made"]

            new_headers = base_headers + Config.PRODUCTS + tail_headers

            if current_headers != new_headers:
                ws.update("A1", [new_headers], value_input_option="RAW")
                logger.info("Shifts headers updated with new columns")
            else:
                logger.info("Shifts headers already up to date")

        except gspread.WorksheetNotFound:
            logger.error(f"Worksheet '{Config.SHEET_NAME}' not found")
            raise

    def run(self) -> None:
        """Run all initialization steps."""
        logger.info("Starting sheets initialization...")

        try:
            self.init_employee_settings()
            self.init_dynamic_rates()
            self.init_ranks()
            self.init_employee_ranks()
            self.init_active_bonuses()
            self.update_shifts_headers()

            logger.info("✅ All sheets initialized successfully!")

        except Exception as e:
            logger.error(f"❌ Initialization failed: {e}")
            raise


def main():
    """Main entry point."""
    try:
        Config.validate()
        initializer = SheetsInitializer()
        initializer.run()

        print("\n" + "="*60)
        print("✅ Initialization completed successfully!")
        print("="*60)
        print("\nNew sheets created:")
        print("  1. EmployeeSettings - Employee hourly wage and base commission")
        print("  2. DynamicRates - Dynamic commission rates based on daily sales")
        print("  3. Ranks - Rank system configuration")
        print("  4. EmployeeRanks - Current employee ranks")
        print("  5. ActiveBonuses - Active bonuses to be applied")
        print("\nShifts sheet updated with new columns:")
        print("  - Worked hours/shift")
        print("  - %")
        print("  - Total per hour")
        print("  - Commissions")
        print("  - Total made (reordered)")
        print("\n" + "="*60)

    except Exception as e:
        print(f"\n❌ Error: {e}")
        return 1

    return 0


if __name__ == "__main__":
    exit(main())
