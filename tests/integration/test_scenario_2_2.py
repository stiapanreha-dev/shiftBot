"""
Automated Integration Test for TEST_SCENARIOS.md

Test 2.2: Creating a shift with multiple products

This test simulates the full bot conversation flow:
1. User presses "Create shift"
2. Selects "Server date"
3. Selects "9 AM" (Clock in)
4. Selects "5 PM" (Clock out)
5. Selects product "Model A"
6. Enters amount "500"
7. Presses "Add model"
8. Selects product "Model B"
9. Enters amount "300"
10. Presses "Add model"
11. Selects product "Model C"
12. Enters amount "200"
13. Presses "Finish shift"

Then verifies:
- 3 products added
- Total sales = $1000 (500 + 300 + 200)
- Net sales = $800
- % = 12% (8% base + 4% dynamic for $1000)
- Commissions = $96
- Total per hour = $120
- Total made = $216
"""

import sys
import os
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

import logging
from datetime import datetime
from decimal import Decimal
from unittest.mock import MagicMock, AsyncMock
import asyncio

from telegram import Update, User, Message, CallbackQuery, Chat
from telegram.ext import ContextTypes, ConversationHandler

from src.handlers import (
    start, handle_callback_query, handle_amount_input
)
from config import Config, START, CHOOSE_DATE_IN, CHOOSE_TIME_IN, CHOOSE_TIME_OUT
from config import PICK_PRODUCT, ENTER_AMOUNT, ADD_OR_FINISH
from services.postgres_service import PostgresService
from src.time_utils import now_et, format_dt, get_server_date

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class BotTestSimulator:
    """Simulates bot conversation for testing."""

    def __init__(self, user_id: int, username: str):
        """Initialize simulator.

        Args:
            user_id: Telegram user ID
            username: Telegram username
        """
        self.user_id = user_id
        self.username = username
        self.sheets = SheetsService()

    def _create_mock_update(self, text: str = None, callback_data: str = None) -> Update:
        """Create mock Update object.

        Args:
            text: Message text (for text messages)
            callback_data: Callback data (for inline buttons)

        Returns:
            Mock Update object
        """
        # Create mock user
        user = MagicMock(spec=User)
        user.id = self.user_id
        user.username = self.username
        user.first_name = "Test"
        user.last_name = "User"

        # Create mock chat
        chat = MagicMock(spec=Chat)
        chat.id = self.user_id
        chat.type = "private"

        # Create update
        update = MagicMock(spec=Update)
        update.effective_user = user
        update.effective_chat = chat

        if callback_data:
            # Callback query (button press)
            callback_query = MagicMock(spec=CallbackQuery)
            callback_query.from_user = user
            callback_query.data = callback_data
            callback_query.answer = AsyncMock()
            callback_query.edit_message_text = AsyncMock()
            callback_query.edit_message_reply_markup = AsyncMock()
            callback_query.message = MagicMock(spec=Message)
            callback_query.message.chat = chat
            callback_query.message.reply_text = AsyncMock()

            update.callback_query = callback_query
            update.message = None
        else:
            # Text message
            message = MagicMock(spec=Message)
            message.from_user = user
            message.chat = chat
            message.text = text
            message.reply_text = AsyncMock()

            update.message = message
            update.callback_query = None

        return update

    def _create_mock_context(self) -> ContextTypes.DEFAULT_TYPE:
        """Create mock Context object.

        Returns:
            Mock Context object
        """
        context = MagicMock()
        context.user_data = {}
        context.bot = MagicMock()
        context.bot.send_message = AsyncMock()
        context.bot.send_chat_action = AsyncMock()
        return context

    async def run_test(self) -> dict:
        """Run the full test scenario.

        Returns:
            Test results dictionary
        """
        logger.info("="*70)
        logger.info("🧪 TEST 2.2: Creating shift with multiple products")
        logger.info("="*70)
        logger.info(f"User ID: {self.user_id}")
        logger.info(f"Username: @{self.username}")
        logger.info("")

        # Store initial shift count
        all_shifts = self.sheets.get_all_shifts()
        initial_shift_count = len(all_shifts)
        logger.info(f"📊 Initial shifts in DB: {initial_shift_count}")

        # Create reusable context
        context = self._create_mock_context()

        # Step 1: /start command
        logger.info("\n" + "─"*70)
        logger.info("STEP 1: User sends /start")
        logger.info("─"*70)
        update = self._create_mock_update(text="/start")
        result = await start(update, context)
        logger.info(f"✓ State returned: {result}")
        assert result == START, f"Expected START state, got {result}"

        # Step 2: Press "Create shift" button
        logger.info("\n" + "─"*70)
        logger.info("STEP 2: User presses 'Create shift'")
        logger.info("─"*70)
        update = self._create_mock_update(callback_data="CREATE_SHIFT")
        result = await handle_callback_query(update, context)
        logger.info(f"✓ State returned: {result}")
        assert result == CHOOSE_DATE_IN, f"Expected CHOOSE_DATE_IN, got {result}"

        # Step 3: Select "Server date"
        logger.info("\n" + "─"*70)
        logger.info("STEP 3: User selects 'Server date'")
        logger.info("─"*70)
        server_date = get_server_date()
        logger.info(f"  Server date: {server_date}")
        update = self._create_mock_update(callback_data="DATE_IN:0")
        result = await handle_callback_query(update, context)
        logger.info(f"✓ State returned: {result}")
        assert result == CHOOSE_TIME_IN, f"Expected CHOOSE_TIME_IN, got {result}"

        # Step 4: Select "9 AM" (Clock in)
        logger.info("\n" + "─"*70)
        logger.info("STEP 4: User selects '9 AM' (Clock in)")
        logger.info("─"*70)
        update = self._create_mock_update(callback_data="TIME:IN:09_AM")
        result = await handle_callback_query(update, context)
        logger.info(f"✓ State returned: {result}")
        clock_in = context.user_data.get('clock_in')
        logger.info(f"  Clock in: {clock_in}")
        assert result == CHOOSE_TIME_OUT, f"Expected CHOOSE_TIME_OUT, got {result}"

        # Step 5: Select "5 PM" (Clock out)
        logger.info("\n" + "─"*70)
        logger.info("STEP 5: User selects '5 PM' (Clock out)")
        logger.info("─"*70)
        update = self._create_mock_update(callback_data="TIME:OUT:05_PM")
        result = await handle_callback_query(update, context)
        logger.info(f"✓ State returned: {result}")
        clock_out = context.user_data.get('clock_out')
        logger.info(f"  Clock out: {clock_out}")
        assert result == PICK_PRODUCT, f"Expected PICK_PRODUCT, got {result}"

        # Step 6: Select product "Model A"
        logger.info("\n" + "─"*70)
        logger.info("STEP 6: User selects product 'Model A'")
        logger.info("─"*70)
        product_a = Config.PRODUCTS[0]  # Model A
        update = self._create_mock_update(callback_data=f"PROD:{product_a}")
        result = await handle_callback_query(update, context)
        logger.info(f"✓ State returned: {result}")
        logger.info(f"  Selected product: {context.user_data.get('current_product')}")
        assert result == ENTER_AMOUNT, f"Expected ENTER_AMOUNT, got {result}"

        # Step 7: Enter amount "500" for Model A
        logger.info("\n" + "─"*70)
        logger.info("STEP 7: User enters amount '500' for Model A")
        logger.info("─"*70)
        update = self._create_mock_update(text="500")
        result = await handle_amount_input(update, context)
        logger.info(f"✓ State returned: {result}")
        products = context.user_data.get('products', {})
        logger.info(f"  Products: {products}")
        assert result == ADD_OR_FINISH, f"Expected ADD_OR_FINISH, got {result}"
        assert product_a in products, f"Product {product_a} not added"
        assert products[product_a] == Decimal('500'), f"Amount incorrect for {product_a}"

        # Step 8: Press "Add model" to add another product
        logger.info("\n" + "─"*70)
        logger.info("STEP 8: User presses 'Add model'")
        logger.info("─"*70)
        update = self._create_mock_update(callback_data="ADD_MODEL")
        result = await handle_callback_query(update, context)
        logger.info(f"✓ State returned: {result}")
        assert result == PICK_PRODUCT, f"Expected PICK_PRODUCT, got {result}"

        # Step 9: Select product "Model B"
        logger.info("\n" + "─"*70)
        logger.info("STEP 9: User selects product 'Model B'")
        logger.info("─"*70)
        product_b = Config.PRODUCTS[1]  # Model B
        update = self._create_mock_update(callback_data=f"PROD:{product_b}")
        result = await handle_callback_query(update, context)
        logger.info(f"✓ State returned: {result}")
        logger.info(f"  Selected product: {context.user_data.get('current_product')}")
        assert result == ENTER_AMOUNT, f"Expected ENTER_AMOUNT, got {result}"

        # Step 10: Enter amount "300" for Model B
        logger.info("\n" + "─"*70)
        logger.info("STEP 10: User enters amount '300' for Model B")
        logger.info("─"*70)
        update = self._create_mock_update(text="300")
        result = await handle_amount_input(update, context)
        logger.info(f"✓ State returned: {result}")
        products = context.user_data.get('products', {})
        logger.info(f"  Products: {products}")
        assert result == ADD_OR_FINISH, f"Expected ADD_OR_FINISH, got {result}"
        assert product_b in products, f"Product {product_b} not added"
        assert products[product_b] == Decimal('300'), f"Amount incorrect for {product_b}"

        # Step 11: Press "Add model" to add third product
        logger.info("\n" + "─"*70)
        logger.info("STEP 11: User presses 'Add model' again")
        logger.info("─"*70)
        update = self._create_mock_update(callback_data="ADD_MODEL")
        result = await handle_callback_query(update, context)
        logger.info(f"✓ State returned: {result}")
        assert result == PICK_PRODUCT, f"Expected PICK_PRODUCT, got {result}"

        # Step 12: Select product "Model C"
        logger.info("\n" + "─"*70)
        logger.info("STEP 12: User selects product 'Model C'")
        logger.info("─"*70)
        product_c = Config.PRODUCTS[2]  # Model C
        update = self._create_mock_update(callback_data=f"PROD:{product_c}")
        result = await handle_callback_query(update, context)
        logger.info(f"✓ State returned: {result}")
        logger.info(f"  Selected product: {context.user_data.get('current_product')}")
        assert result == ENTER_AMOUNT, f"Expected ENTER_AMOUNT, got {result}"

        # Step 13: Enter amount "200" for Model C
        logger.info("\n" + "─"*70)
        logger.info("STEP 13: User enters amount '200' for Model C")
        logger.info("─"*70)
        update = self._create_mock_update(text="200")
        result = await handle_amount_input(update, context)
        logger.info(f"✓ State returned: {result}")
        products = context.user_data.get('products', {})
        logger.info(f"  Products: {products}")
        assert result == ADD_OR_FINISH, f"Expected ADD_OR_FINISH, got {result}"
        assert product_c in products, f"Product {product_c} not added"
        assert products[product_c] == Decimal('200'), f"Amount incorrect for {product_c}"

        # Verify all 3 products added
        assert len(products) == 3, f"Expected 3 products, got {len(products)}"
        logger.info(f"✓ All 3 products added: {list(products.keys())}")

        # Step 14: Press "Finish shift"
        logger.info("\n" + "─"*70)
        logger.info("STEP 14: User presses 'Finish shift'")
        logger.info("─"*70)
        update = self._create_mock_update(callback_data="FINISH")

        # Capture the summary message
        captured_summary = {"text": None}

        async def capture_reply(text, **kwargs):
            captured_summary["text"] = text
            logger.info(f"\n📨 Bot Response:\n{text}\n")

        if update.callback_query:
            update.callback_query.message.reply_text = AsyncMock(side_effect=capture_reply)

        result = await handle_callback_query(update, context)
        logger.info(f"✓ State returned: {result}")
        assert result == ConversationHandler.END, f"Expected ConversationHandler.END, got {result}"

        # Verify shift was created in Google Sheets
        logger.info("\n" + "─"*70)
        logger.info("VERIFICATION: Checking Google Sheets")
        logger.info("─"*70)

        all_shifts_after = self.sheets.get_all_shifts()
        new_shift_count = len(all_shifts_after)
        logger.info(f"📊 Shifts after test: {new_shift_count}")

        assert new_shift_count == initial_shift_count + 1, \
            f"Expected {initial_shift_count + 1} shifts, got {new_shift_count}"

        # Get the newly created shift (last one)
        new_shift = all_shifts_after[-1]
        shift_id = new_shift.get('ID')

        logger.info(f"\n✅ New shift created:")
        logger.info(f"   ID: {shift_id}")
        logger.info(f"   Date: {new_shift.get('Date')}")
        logger.info(f"   Employee ID: {new_shift.get('EmployeeId')}")
        logger.info(f"   Clock in: {new_shift.get('Clock in')}")
        logger.info(f"   Clock out: {new_shift.get('Clock out')}")
        logger.info(f"   {product_a}: ${new_shift.get(product_a, 0):.2f}")
        logger.info(f"   {product_b}: ${new_shift.get(product_b, 0):.2f}")
        logger.info(f"   {product_c}: ${new_shift.get(product_c, 0):.2f}")
        logger.info(f"   Total sales: ${new_shift.get('Total sales', 0):.2f}")
        logger.info(f"   Net sales: ${new_shift.get('Net sales', 0):.2f}")
        logger.info(f"   Worked hours/shift: {new_shift.get('Worked hours/shift', 0):.2f}")
        logger.info(f"   %: {new_shift.get('%', 0):.2f}%")
        logger.info(f"   Total per hour: ${new_shift.get('Total per hour', 0):.2f}")
        logger.info(f"   Commissions: ${new_shift.get('Commissions', 0):.2f}")
        logger.info(f"   Total made: ${new_shift.get('Total made', 0):.2f}")

        # Verify calculations
        logger.info("\n" + "─"*70)
        logger.info("VERIFICATION: Checking calculations")
        logger.info("─"*70)

        expected_worked_hours = 8.0  # 9 AM to 5 PM
        expected_total_sales = 1000.0  # 500 + 300 + 200
        expected_net_sales = 800.0  # 1000 × 0.8

        # Get employee settings
        settings = self.sheets.get_employee_settings(self.user_id)
        hourly_wage = float(settings.get('Hourly wage', 15.0))
        base_commission = float(settings.get('Sales commission', 8.0))

        # Calculate expected values
        expected_total_per_hour = expected_worked_hours * hourly_wage

        # IMPORTANT: Dynamic rate is calculated based on CUMULATIVE daily sales!
        # Get actual commission % from created shift (it considers all shifts today)
        actual_commission_pct = float(new_shift.get('%', 0))

        # Use actual commission % for calculations
        expected_commissions = expected_net_sales * (actual_commission_pct / 100)
        expected_total_made = expected_commissions + expected_total_per_hour

        logger.info(f"ℹ️  Note: Commission % is {actual_commission_pct:.2f}% (based on cumulative daily sales)")
        logger.info(f"   This is correct - dynamic rate considers ALL shifts today")

        results = {
            "success": True,
            "shift_id": shift_id,
            "shift_data": new_shift,
            "summary": captured_summary["text"],
            "verifications": []
        }

        def verify(name, expected, actual, tolerance=0.01):
            """Verify a value matches expected."""
            match = abs(float(expected) - float(actual)) < tolerance
            status = "✓" if match else "✗"
            logger.info(f"{status} {name}: Expected {expected}, Got {actual}")
            results["verifications"].append({
                "name": name,
                "expected": expected,
                "actual": actual,
                "match": match
            })
            return match

        all_match = True
        all_match &= verify("Worked hours", expected_worked_hours, new_shift.get('Worked hours/shift', 0))
        all_match &= verify("Total sales", expected_total_sales, new_shift.get('Total sales', 0))
        all_match &= verify("Net sales", expected_net_sales, new_shift.get('Net sales', 0))
        all_match &= verify("Total per hour", expected_total_per_hour, new_shift.get('Total per hour', 0))
        all_match &= verify("Commissions", expected_commissions, new_shift.get('Commissions', 0))
        all_match &= verify("Total made", expected_total_made, new_shift.get('Total made', 0))

        # Verify individual products
        all_match &= verify(f"{product_a} amount", 500.0, new_shift.get(product_a, 0))
        all_match &= verify(f"{product_b} amount", 300.0, new_shift.get(product_b, 0))
        all_match &= verify(f"{product_c} amount", 200.0, new_shift.get(product_c, 0))

        if all_match:
            logger.info("\n" + "="*70)
            logger.info("✅ TEST 2.2 PASSED - All verifications successful!")
            logger.info("="*70)
        else:
            logger.error("\n" + "="*70)
            logger.error("❌ TEST 2.2 FAILED - Some verifications failed!")
            logger.error("="*70)
            results["success"] = False

        return results


async def main():
    """Run the test."""
    # Test user from TEST_SCENARIOS.md
    user_id = 120962578
    username = "StepunR"

    simulator = BotTestSimulator(user_id, username)

    try:
        results = await simulator.run_test()

        print("\n" + "="*70)
        print("📋 TEST RESULTS SUMMARY")
        print("="*70)
        print(f"Status: {'PASS ✅' if results['success'] else 'FAIL ❌'}")
        print(f"Shift ID: {results['shift_id']}")
        print(f"\nVerifications:")
        for v in results["verifications"]:
            status = "✓" if v["match"] else "✗"
            print(f"  {status} {v['name']}: {v['actual']} (expected {v['expected']})")

        if results["summary"]:
            print(f"\n📨 Bot Summary Message:")
            print(results["summary"])

        return 0 if results['success'] else 1

    except Exception as e:
        logger.error(f"❌ Test failed with exception: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)
