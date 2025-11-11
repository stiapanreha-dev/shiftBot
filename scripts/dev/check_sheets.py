"""Check and initialize Google Sheets structure."""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))
import logging
from sheets_service import SheetsService
from config import Config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def main():
    """Check and initialize Google Sheets."""
    try:
        logger.info("Initializing Google Sheets service...")
        sheets = SheetsService()

        logger.info(f"Spreadsheet ID: {Config.SPREADSHEET_ID}")
        logger.info(f"Sheet name: {Config.SHEET_NAME}")
        logger.info(f"Products: {', '.join(Config.PRODUCTS)}")

        logger.info("\nChecking worksheet...")
        ws = sheets.get_worksheet()

        logger.info(f"✅ Worksheet '{Config.SHEET_NAME}' found/created")

        logger.info("\nEnsuring headers...")
        sheets.ensure_headers(ws)

        # Read and display headers
        headers = ws.row_values(1)
        logger.info(f"\n✅ Headers set successfully:")
        for i, header in enumerate(headers, 1):
            logger.info(f"   {i}. {header}")

        # Check if there are any records
        all_records = ws.get_all_records()
        logger.info(f"\n📊 Current records count: {len(all_records)}")

        if all_records:
            logger.info(f"\nLast 3 records:")
            for record in all_records[-3:]:
                logger.info(f"   ID {record.get('ID')}: {record.get('EmployeeName')} - {record.get('Date')}")
        else:
            logger.info("\nNo records yet. Table is ready for new shifts.")

        logger.info("\n✅ Google Sheets is ready!")

    except Exception as e:
        logger.error(f"\n❌ Error: {e}")
        raise


if __name__ == "__main__":
    main()
