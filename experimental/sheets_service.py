"""Google Sheets service for shift data management."""

import logging
from typing import Dict, List, Optional
from decimal import Decimal

import gspread
from gspread.exceptions import APIError, WorksheetNotFound

from config import Config
from src.time_utils import parse_dt

logger = logging.getLogger(__name__)


class SheetsService:
    """Service for managing shift data in Google Sheets."""

    def __init__(self, cache_manager=None):
        """Initialize sheets service with credentials from config.

        Args:
            cache_manager: Optional CacheManager instance for caching support.
                          If None, a dummy cache manager will be created.
        """
        try:
            self.client = gspread.service_account(filename=Config.GOOGLE_SA_JSON)
            self.spreadsheet = self.client.open_by_key(Config.SPREADSHEET_ID)
            logger.info("Google Sheets client initialized successfully")

            # Setup cache manager
            if cache_manager is None:
                # Create dummy cache manager that does nothing (for backward compatibility)
                from cache_manager import DummyCacheManager
                self.cache_manager = DummyCacheManager()
                logger.info("Using DummyCacheManager (no caching)")
            else:
                self.cache_manager = cache_manager
                logger.info("Using CacheManager (caching enabled)")

        except Exception as e:
            logger.error(f"Failed to initialize Google Sheets client: {e}")
            raise

    def get_worksheet(self) -> gspread.Worksheet:
        """Get or create the shifts worksheet.

        Returns:
            Worksheet object.

        Raises:
            APIError: If failed to access worksheet.
        """
        try:
            return self.spreadsheet.worksheet(Config.SHEET_NAME)
        except WorksheetNotFound:
            logger.info(f"Worksheet '{Config.SHEET_NAME}' not found, creating...")
            ws = self.spreadsheet.add_worksheet(
                title=Config.SHEET_NAME, rows=100, cols=20
            )
            self.ensure_headers(ws)
            return ws
        except APIError as e:
            logger.error(f"Failed to get worksheet: {e}")
            raise

    def ensure_headers(self, ws: Optional[gspread.Worksheet] = None) -> None:
        """Ensure worksheet has correct headers.

        Args:
            ws: Worksheet object (optional, will get if not provided).
        """
        if ws is None:
            ws = self.get_worksheet()

        base_headers = ["ID", "Date", "EmployeeId", "EmployeeName", "Clock in", "Clock out", "Worked hours/shift"]
        tail_headers = ["Total sales", "Net sales", "%", "Total per hour", "Commissions", "Total made"]
        expected_headers = base_headers + Config.PRODUCTS + tail_headers

        try:
            current_headers = ws.row_values(1)

            if current_headers != expected_headers:
                if not current_headers:
                    # No headers, set them
                    ws.update("A1", [expected_headers], value_input_option="RAW")
                    logger.info("Headers created")
                else:
                    # Update/sync headers
                    ws.update("A1", [expected_headers], value_input_option="RAW")
                    logger.info("Headers updated")
        except APIError as e:
            logger.error(f"Failed to ensure headers: {e}")
            raise

    def get_next_id(self) -> int:
        """Get next available ID for shift.

        Returns:
            Next ID value.
        """
        try:
            ws = self.get_worksheet()
            ids = ws.col_values(1)[1:]  # Skip header

            if not ids:
                return 1

            # Find last valid ID
            for id_str in reversed(ids):
                try:
                    last_id = int(id_str.strip())
                    return last_id + 1
                except (ValueError, AttributeError):
                    continue

            return 1
        except APIError as e:
            logger.error(f"Failed to get next ID: {e}")
            raise

    def create_shift(self, shift_data: Dict) -> int:
        """Create new shift record in sheets with new calculation logic.

        Args:
            shift_data: Dictionary with shift information.

        Returns:
            Created shift ID.

        Raises:
            APIError: If failed to create shift.
        """
        try:
            ws = self.get_worksheet()
            self.ensure_headers(ws)

            shift_id = self.get_next_id()
            headers = ws.row_values(1)

            employee_id = shift_data["employee_id"]
            clock_in = shift_data["clock_in"]
            clock_out = shift_data["clock_out"]

            # 1. Get employee settings
            settings = self.get_employee_settings(employee_id)
            if not settings:
                # Create default settings
                self.create_default_employee_settings(employee_id)
                settings = {"Hourly wage": 15.0, "Sales commission": 8.0}

            hourly_wage = Decimal(str(settings["Hourly wage"]))
            base_commission = Decimal(str(settings["Sales commission"]))

            # 2. Calculate worked hours
            clock_in_dt = parse_dt(clock_in)
            clock_out_dt = parse_dt(clock_out)
            worked_hours = (clock_out_dt - clock_in_dt).total_seconds() / 3600
            worked_hours_decimal = Decimal(str(worked_hours))

            # 3. Calculate Total per hour
            total_per_hour = worked_hours_decimal * hourly_wage

            # 4. Calculate Total sales
            products = shift_data.get("products", {})
            total_sales = sum(Decimal(str(v)) for v in products.values())

            # 5. Calculate Net sales (Total sales × 0.8)
            net_sales = total_sales * Decimal("0.8")

            # 6. Calculate dynamic commission rate
            shift_date = shift_data["date"]
            dynamic_rate = Decimal(str(self.calculate_dynamic_rate(employee_id, shift_date, total_sales)))

            # 7. Calculate total commission percentage
            commission_percent = base_commission + dynamic_rate

            # 8. Apply active bonuses (percent_next, double_commission, percent_prev, percent_all)
            active_bonuses = self.get_active_bonuses(employee_id)
            bonus_additions = Decimal("0")

            # Create temporary shift dict for complex bonuses
            temp_shift = {
                "Date": shift_date,
                "Clock in": clock_in,
                "EmployeeId": employee_id,
            }
            # Add products to temp shift
            for product, amount in products.items():
                temp_shift[product] = amount

            for bonus in active_bonuses:
                bonus_type = bonus.get("Bonus Type", "")
                bonus_value = Decimal(str(bonus.get("Value", 0)))

                if bonus_type == "percent_next":
                    commission_percent += bonus_value
                    self.apply_bonus(bonus.get("ID"), shift_id)
                    logger.info(f"Applied percent_next bonus: +{bonus_value}%")

                elif bonus_type == "double_commission":
                    commission_percent *= Decimal("2")
                    self.apply_bonus(bonus.get("ID"), shift_id)
                    logger.info(f"Applied double_commission bonus")

                elif bonus_type == "percent_prev":
                    # Complex bonus: +X% from previous shift chatter
                    prev_bonus = self.apply_percent_prev_bonus(employee_id, temp_shift, float(bonus_value))
                    bonus_additions += prev_bonus
                    self.apply_bonus(bonus.get("ID"), shift_id)
                    logger.info(f"Applied percent_prev bonus: +${prev_bonus:.2f}")

                elif bonus_type == "percent_all":
                    # Complex bonus: +X% from all other chatters
                    all_bonus = self.apply_percent_all_bonus(employee_id, temp_shift, float(bonus_value))
                    bonus_additions += all_bonus
                    self.apply_bonus(bonus.get("ID"), shift_id)
                    logger.info(f"Applied percent_all bonus: +${all_bonus:.2f}")

                elif bonus_type in ["flat", "flat_immediate"]:
                    # Add to total_made at the end
                    bonus_additions += bonus_value
                    self.apply_bonus(bonus.get("ID"), shift_id)
                    logger.info(f"Applied flat bonus: +${bonus_value}")

            # 9. Calculate Commissions
            commissions = net_sales * (commission_percent / Decimal("100"))

            # 10. Calculate Total made
            total_made = commissions + total_per_hour + bonus_additions

            # Build row data
            row_data = {
                "ID": shift_id,
                "Date": shift_data["date"],
                "EmployeeId": shift_data["employee_id"],
                "EmployeeName": shift_data["employee_name"],
                "Clock in": clock_in,
                "Clock out": clock_out,
                "Worked hours/shift": f"{worked_hours:.2f}",
                "Total sales": f"{total_sales:.2f}",
                "Net sales": f"{net_sales:.2f}",
                "%": f"{commission_percent:.2f}",
                "Total per hour": f"{total_per_hour:.2f}",
                "Commissions": f"{commissions:.2f}",
                "Total made": f"{total_made:.2f}",
            }

            # Add product values
            for product, amount in products.items():
                row_data[product] = f"{Decimal(str(amount)):.2f}"

            # Build row in correct order
            row = [row_data.get(h, "") for h in headers]

            ws.append_row(row, value_input_option="RAW")
            logger.info(f"Shift {shift_id} created successfully")
            logger.info(f"  Worked hours: {worked_hours:.2f}, Total per hour: ${total_per_hour:.2f}")
            logger.info(f"  Commission %: {commission_percent:.2f}%, Commissions: ${commissions:.2f}")
            logger.info(f"  Total made: ${total_made:.2f}")

            # Invalidate cache: employee settings might have changed due to shift creation
            self.cache_manager.invalidate_namespace("employee_settings")
            logger.debug(f"✗ Invalidated cache: employee_settings (shift {shift_id} created)")

            return shift_id
        except APIError as e:
            logger.error(f"Failed to create shift: {e}")
            raise

    def find_row_by_id(self, shift_id: int) -> Optional[int]:
        """Find row number by shift ID.

        Args:
            shift_id: Shift ID to find.

        Returns:
            Row number (1-indexed) or None if not found.
        """
        try:
            ws = self.get_worksheet()
            ids = ws.col_values(1)[1:]  # Skip header

            for idx, id_str in enumerate(ids, start=2):
                try:
                    if int(id_str.strip()) == shift_id:
                        return idx
                except (ValueError, AttributeError):
                    continue

            return None
        except APIError as e:
            logger.error(f"Failed to find row by ID: {e}")
            raise

    def get_shift_by_id(self, shift_id: int) -> Optional[Dict]:
        """Get shift data by ID.

        Args:
            shift_id: Shift ID.

        Returns:
            Dict with shift data or None if not found.
        """
        try:
            ws = self.get_worksheet()
            row_idx = self.find_row_by_id(shift_id)

            if not row_idx:
                return None

            headers = ws.row_values(1)
            row_vals = ws.row_values(row_idx)

            return {
                h: (row_vals[i] if i < len(row_vals) else "")
                for i, h in enumerate(headers)
            }
        except APIError as e:
            logger.error(f"Failed to get shift by ID: {e}")
            raise

    def update_shift_field(self, shift_id: int, field: str, value: str) -> bool:
        """Update single field in shift record.

        Args:
            shift_id: Shift ID.
            field: Field name to update.
            value: New value.

        Returns:
            True if updated successfully, False if not found.
        """
        try:
            ws = self.get_worksheet()
            row_idx = self.find_row_by_id(shift_id)

            if not row_idx:
                return False

            headers = ws.row_values(1)

            if field not in headers:
                logger.error(f"Field '{field}' not found in headers")
                return False

            col_idx = headers.index(field) + 1
            # Use RAW mode to prevent Google Sheets from reformatting dates
            col_letter = chr(64 + col_idx)  # Convert to A, B, C...
            cell_range = f"{col_letter}{row_idx}"
            ws.update(cell_range, [[value]], value_input_option="RAW")
            logger.info(f"Shift {shift_id} field '{field}' updated to '{value}'")

            # Invalidate cache: shift was updated
            self.cache_manager.invalidate_key("shift", str(shift_id))
            logger.debug(f"✗ Invalidated cache: shift[{shift_id}] (field '{field}' updated)")

            return True
        except APIError as e:
            logger.error(f"Failed to update shift field: {e}")
            raise

    def update_total_sales(self, shift_id: int, total_sales: Decimal) -> bool:
        """Update Total sales and recalculate all dependent fields properly.

        Args:
            shift_id: Shift ID.
            total_sales: New total sales value.

        Returns:
            True if updated successfully, False if not found.
        """
        try:
            ws = self.get_worksheet()
            row_idx = self.find_row_by_id(shift_id)

            if not row_idx:
                return False

            headers = ws.row_values(1)
            row_vals = ws.row_values(row_idx)

            # Get current shift data
            shift_data = {h: (row_vals[i] if i < len(row_vals) else "") for i, h in enumerate(headers)}

            employee_id = int(shift_data.get("EmployeeId", 0))
            clock_in = shift_data.get("Clock in", "")
            clock_out = shift_data.get("Clock out", "")
            shift_date = shift_data.get("Date", "")

            # 1. Get employee settings
            settings = self.get_employee_settings(employee_id)
            if not settings:
                settings = {"Hourly wage": 15.0, "Sales commission": 8.0}

            hourly_wage = Decimal(str(settings["Hourly wage"]))
            base_commission = Decimal(str(settings["Sales commission"]))

            # 2. Calculate worked hours
            clock_in_dt = parse_dt(clock_in)
            clock_out_dt = parse_dt(clock_out)
            worked_hours = (clock_out_dt - clock_in_dt).total_seconds() / 3600
            worked_hours_decimal = Decimal(str(worked_hours))

            # 3. Calculate Total per hour
            total_per_hour = worked_hours_decimal * hourly_wage

            # 4. Calculate Net sales (Total sales × 0.8)
            net_sales = total_sales * Decimal("0.8")

            # 5. Calculate dynamic commission rate
            dynamic_rate = Decimal(str(self.calculate_dynamic_rate(employee_id, shift_date, total_sales)))

            # 6. Calculate total commission percentage
            commission_percent = base_commission + dynamic_rate

            # 7. Calculate Commissions
            commissions = net_sales * (commission_percent / Decimal("100"))

            # 8. Calculate Total made (including bonus_additions if any from shift data)
            # Note: We don't re-apply bonuses, they were already applied during shift creation
            total_made = commissions + total_per_hour

            # Update all calculated fields
            updates = [
                ("Total sales", f"{total_sales:.2f}"),
                ("Net sales", f"{net_sales:.2f}"),
                ("%", f"{commission_percent:.2f}"),
                ("Total per hour", f"{total_per_hour:.2f}"),
                ("Commissions", f"{commissions:.2f}"),
                ("Total made", f"{total_made:.2f}"),
            ]

            for field, value in updates:
                if field in headers:
                    col_idx = headers.index(field) + 1
                    col_letter = chr(64 + col_idx)  # Convert to A, B, C...
                    cell_range = f"{col_letter}{row_idx}"
                    ws.update(cell_range, [[value]], value_input_option="RAW")

            logger.info(f"Shift {shift_id} totals updated: Total sales={total_sales:.2f}, "
                       f"Commission %={commission_percent:.2f}, Total made={total_made:.2f}")

            # Invalidate cache: shift and related data were updated
            self.cache_manager.invalidate_key("shift", str(shift_id))
            self.cache_manager.invalidate_key("shift_bonuses", str(shift_id))
            logger.debug(f"✗ Invalidated cache: shift[{shift_id}], shift_bonuses[{shift_id}] (totals updated)")

            return True
        except APIError as e:
            logger.error(f"Failed to update totals: {e}")
            raise

    def get_last_shifts(self, employee_id: int, limit: int = 3) -> List[Dict]:
        """Get last N shifts for employee sorted by date (newest first).

        Args:
            employee_id: Employee ID (Telegram user ID).
            limit: Number of shifts to return.

        Returns:
            List of shift dictionaries.
        """
        try:
            ws = self.get_worksheet()
            all_records = ws.get_all_records()

            # Filter by employee
            employee_shifts = [
                r for r in all_records
                if str(r.get("EmployeeId")) == str(employee_id)
            ]

            # Sort by Date (newest first)
            def parse_date_safe(record):
                try:
                    return parse_dt(record.get("Date", ""))
                except:
                    return parse_dt("1970/01/01 00:00:00")

            employee_shifts.sort(key=parse_date_safe, reverse=True)

            return employee_shifts[:limit]
        except APIError as e:
            logger.error(f"Failed to get last shifts: {e}")
            raise

    def get_all_shifts(self) -> List[Dict]:
        """Get all shifts from Shifts table.

        Returns:
            List of all shift dictionaries.
        """
        try:
            ws = self.get_worksheet()
            all_records = ws.get_all_records()
            return all_records
        except APIError as e:
            logger.error(f"Failed to get all shifts: {e}")
            raise

    # ==================== EmployeeSettings Methods ====================

    def get_employee_settings(self, employee_id: int) -> Optional[Dict]:
        """Get employee settings (hourly wage and base commission).

        Args:
            employee_id: Telegram user ID.

        Returns:
            Dict with 'Hourly wage' and 'Sales commission' or None if not found.
        """
        try:
            ws = self.spreadsheet.worksheet("EmployeeSettings")
            all_records = ws.get_all_records()

            for record in all_records:
                if str(record.get("EmployeeId")) == str(employee_id):
                    return {
                        "Hourly wage": float(record.get("Hourly wage", 15.0)),
                        "Sales commission": float(record.get("Sales commission", 8.0)),
                    }

            logger.warning(f"Employee settings not found for {employee_id}, using defaults")
            return None
        except (WorksheetNotFound, APIError) as e:
            logger.error(f"Failed to get employee settings: {e}")
            return None

    def create_default_employee_settings(self, employee_id: int) -> None:
        """Create default employee settings.

        Args:
            employee_id: Telegram user ID.
        """
        try:
            ws = self.spreadsheet.worksheet("EmployeeSettings")
            default_data = [str(employee_id), "15.00", "8.0"]
            ws.append_row(default_data, value_input_option="RAW")
            logger.info(f"Default employee settings created for {employee_id}")
        except (WorksheetNotFound, APIError) as e:
            logger.error(f"Failed to create employee settings: {e}")

    # ==================== DynamicRates Methods ====================

    def get_dynamic_rates(self) -> List[Dict]:
        """Get all dynamic rate ranges.

        Returns:
            List of dicts with 'Min Amount', 'Max Amount', 'Percentage'.
        """
        # Try cache first
        cached = self.cache_manager.get("dynamic_rates", "all")
        if cached is not None:
            logger.debug("✓ Cache HIT: dynamic_rates")
            return cached

        logger.debug("✗ Cache MISS: dynamic_rates")
        try:
            ws = self.spreadsheet.worksheet("DynamicRates")
            records = ws.get_all_records()

            rates = []
            for record in records:
                rates.append({
                    "Min Amount": float(record.get("Min Amount", 0)),
                    "Max Amount": float(record.get("Max Amount", 999999)),
                    "Percentage": float(record.get("Percentage", 0)),
                })

            # Cache for 15 minutes (rarely changes)
            self.cache_manager.set("dynamic_rates", "all", rates, ttl=900)

            return rates
        except (WorksheetNotFound, APIError) as e:
            logger.error(f"Failed to get dynamic rates: {e}")
            return []

    def calculate_dynamic_rate(self, employee_id: int, shift_date: str, current_total_sales: Decimal = Decimal("0")) -> float:
        """Calculate dynamic commission rate based on total sales for the day.

        Args:
            employee_id: Telegram user ID.
            shift_date: Date string in format YYYY/MM/DD.
            current_total_sales: Current shift's Total sales to include in calculation.

        Returns:
            Dynamic percentage rate.
        """
        try:
            # Get all shifts for employee on this date
            ws = self.get_worksheet()
            all_records = ws.get_all_records()

            # Extract date part (YYYY/MM/DD) from shift_date
            date_part = shift_date.split(" ")[0] if " " in shift_date else shift_date

            # Sum Total sales for the day (from existing shifts)
            total_sales_today = Decimal("0")
            for record in all_records:
                if str(record.get("EmployeeId")) == str(employee_id):
                    record_date = record.get("Date", "")
                    record_date_part = record_date.split(" ")[0] if " " in record_date else record_date

                    if record_date_part == date_part:
                        sales = record.get("Total sales", 0)
                        if sales:
                            try:
                                total_sales_today += Decimal(str(sales))
                            except:
                                pass

            # Add current shift's Total sales
            total_sales_today += current_total_sales

            # Find matching rate range
            rates = self.get_dynamic_rates()
            for rate in rates:
                min_amt = Decimal(str(rate["Min Amount"]))
                max_amt = Decimal(str(rate["Max Amount"]))

                if min_amt <= total_sales_today < max_amt:
                    return rate["Percentage"]

            return 0.0
        except Exception as e:
            logger.error(f"Failed to calculate dynamic rate: {e}")
            return 0.0

    # ==================== Ranks Methods ====================

    def get_ranks(self) -> List[Dict]:
        """Get all rank definitions.

        Returns:
            List of rank dicts with all fields.
        """
        # Try cache first
        cached = self.cache_manager.get("ranks", "all")
        if cached is not None:
            logger.debug("✓ Cache HIT: ranks")
            return cached

        logger.debug("✗ Cache MISS: ranks")
        try:
            ws = self.spreadsheet.worksheet("Ranks")
            records = ws.get_all_records()

            # Cache for 15 minutes (rarely changes)
            self.cache_manager.set("ranks", "all", records, ttl=900)

            return records
        except (WorksheetNotFound, APIError) as e:
            logger.error(f"Failed to get ranks: {e}")
            return []

    def determine_rank(self, employee_id: int, year: int, month: int) -> str:
        """Determine employee rank based on total sales for the month.

        Args:
            employee_id: Telegram user ID.
            year: Year (e.g., 2025).
            month: Month (1-12).

        Returns:
            Rank name (e.g., 'Hustler').
        """
        try:
            # Get all shifts for the month
            ws = self.get_worksheet()
            all_records = ws.get_all_records()

            # Sum Total sales for the month
            total_sales_month = Decimal("0")
            for record in all_records:
                if str(record.get("EmployeeId")) == str(employee_id):
                    record_date = record.get("Date", "")
                    if record_date:
                        try:
                            dt = parse_dt(record_date)
                            if dt.year == year and dt.month == month:
                                sales = record.get("Total sales", 0)
                                if sales:
                                    total_sales_month += Decimal(str(sales))
                        except:
                            pass

            # Find matching rank
            ranks = self.get_ranks()
            for rank in ranks:
                min_amt = float(rank.get("Min Amount", 0))
                max_amt = float(rank.get("Max Amount", 999999))

                if min_amt <= float(total_sales_month) < max_amt:
                    return rank.get("Rank Name", "Rookie")

            return "Rookie"
        except Exception as e:
            logger.error(f"Failed to determine rank: {e}")
            return "Rookie"

    def get_rank_bonuses(self, rank_name: str) -> List[str]:
        """Get list of bonuses for a rank.

        Args:
            rank_name: Rank name.

        Returns:
            List of bonus codes (e.g., ['flat_10', 'percent_next_1', 'percent_prev_1']).
        """
        try:
            ranks = self.get_ranks()
            for rank in ranks:
                if rank.get("Rank Name") == rank_name:
                    bonuses = [
                        rank.get("Bonus 1"),
                        rank.get("Bonus 2"),
                        rank.get("Bonus 3"),
                    ]
                    return [b for b in bonuses if b and b != "none"]

            return []
        except Exception as e:
            logger.error(f"Failed to get rank bonuses: {e}")
            return []

    def get_rank_text(self, rank_name: str) -> str:
        """Get TEXT field for a rank.

        Args:
            rank_name: Rank name.

        Returns:
            TEXT value for the rank or default message.
        """
        try:
            ranks = self.get_ranks()
            for rank in ranks:
                if rank.get("Rank Name") == rank_name:
                    text = rank.get("TEXT", "")
                    return text if text else "You're really killing it!"

            return "You're really killing it!"
        except Exception as e:
            logger.error(f"Failed to get rank text: {e}")
            return "You're really killing it!"

    # ==================== EmployeeRanks Methods ====================

    def get_employee_rank(self, employee_id: int, year: int, month: int) -> Optional[Dict]:
        """Get employee rank record for specific month.

        Args:
            employee_id: Telegram user ID.
            year: Year.
            month: Month (1-12).

        Returns:
            Dict with rank info or None if not found.
        """
        # Try cache first
        cache_key = f"{employee_id}_{year}_{month}"
        cached = self.cache_manager.get("employee_rank", cache_key)
        if cached is not None:
            logger.debug(f"✓ Cache HIT: employee_rank[{cache_key}]")
            return cached

        logger.debug(f"✗ Cache MISS: employee_rank[{cache_key}]")
        try:
            ws = self.spreadsheet.worksheet("EmployeeRanks")
            all_records = ws.get_all_records()

            for record in all_records:
                if (str(record.get("EmployeeId")) == str(employee_id)
                    and record.get("Year") == year
                    and record.get("Month") == month):

                    # Cache for 5 minutes (can change during the month)
                    self.cache_manager.set("employee_rank", cache_key, record, ttl=300)

                    return record

            # Cache None result too (to avoid repeated API calls)
            self.cache_manager.set("employee_rank", cache_key, None, ttl=300)

            return None
        except (WorksheetNotFound, APIError) as e:
            logger.error(f"Failed to get employee rank: {e}")
            return None

    def update_employee_rank(
        self,
        employee_id: int,
        new_rank: str,
        year: int,
        month: int,
        last_updated: str
    ) -> None:
        """Update or create employee rank record.

        Args:
            employee_id: Telegram user ID.
            new_rank: New rank name.
            year: Year.
            month: Month.
            last_updated: Timestamp string.
        """
        try:
            ws = self.spreadsheet.worksheet("EmployeeRanks")
            all_records = ws.get_all_records()

            # Find existing record
            row_idx = None
            previous_rank = "Rookie"

            for idx, record in enumerate(all_records, start=2):
                if (str(record.get("EmployeeId")) == str(employee_id)
                    and record.get("Year") == year
                    and record.get("Month") == month):
                    row_idx = idx
                    previous_rank = record.get("Current Rank", "Rookie")
                    break

            if row_idx:
                # Update existing record
                headers = ws.row_values(1)
                updates = [
                    ("Current Rank", new_rank),
                    ("Previous Rank", previous_rank),
                    ("Notified", "false"),
                    ("Last Updated", last_updated),
                ]

                for field, value in updates:
                    if field in headers:
                        col_idx = headers.index(field) + 1
                        col_letter = chr(64 + col_idx)
                        cell_range = f"{col_letter}{row_idx}"
                        ws.update(values=[[value]], range_name=cell_range, value_input_option="RAW")

                logger.info(f"Updated rank for employee {employee_id} to {new_rank}")
            else:
                # Create new record
                new_row = [
                    str(employee_id),
                    new_rank,
                    "Rookie",
                    month,
                    year,
                    "false",
                    last_updated
                ]
                ws.append_row(new_row, value_input_option="RAW")
                logger.info(f"Created rank record for employee {employee_id}: {new_rank}")

        except (WorksheetNotFound, APIError) as e:
            logger.error(f"Failed to update employee rank: {e}")

    def mark_rank_notified(self, employee_id: int, year: int, month: int) -> None:
        """Mark employee rank as notified.

        Args:
            employee_id: Telegram user ID.
            year: Year.
            month: Month.
        """
        try:
            ws = self.spreadsheet.worksheet("EmployeeRanks")
            all_records = ws.get_all_records()

            for idx, record in enumerate(all_records, start=2):
                if (str(record.get("EmployeeId")) == str(employee_id)
                    and record.get("Year") == year
                    and record.get("Month") == month):

                    headers = ws.row_values(1)
                    if "Notified" in headers:
                        col_idx = headers.index("Notified") + 1
                        col_letter = chr(64 + col_idx)
                        cell_range = f"{col_letter}{idx}"
                        ws.update(values=[["true"]], range_name=cell_range, value_input_option="RAW")
                        logger.info(f"Marked rank as notified for employee {employee_id}")
                    break

        except (WorksheetNotFound, APIError) as e:
            logger.error(f"Failed to mark rank as notified: {e}")

    # ==================== ActiveBonuses Methods ====================

    def get_active_bonuses(self, employee_id: int) -> List[Dict]:
        """Get active bonuses for employee.

        Args:
            employee_id: Telegram user ID.

        Returns:
            List of bonus dicts.
        """
        try:
            ws = self.spreadsheet.worksheet("ActiveBonuses")
            all_records = ws.get_all_records()

            bonuses = []
            for record in all_records:
                if (str(record.get("EmployeeId")) == str(employee_id)
                    and str(record.get("Applied")).lower() == "false"):
                    bonuses.append(record)

            return bonuses
        except (WorksheetNotFound, APIError) as e:
            logger.error(f"Failed to get active bonuses: {e}")
            return []

    def create_bonus(
        self,
        employee_id: int,
        bonus_type: str,
        value: float,
        created_at: str,
        shift_id: Optional[int] = None
    ) -> int:
        """Create new bonus record.

        Args:
            employee_id: Telegram user ID.
            bonus_type: Type of bonus.
            value: Bonus value.
            created_at: Timestamp string.
            shift_id: Optional shift ID where bonus was applied.

        Returns:
            Bonus ID.
        """
        try:
            ws = self.spreadsheet.worksheet("ActiveBonuses")

            # Get next ID
            ids = ws.col_values(1)[1:]  # Skip header
            next_id = 1
            if ids:
                for id_str in reversed(ids):
                    try:
                        next_id = int(id_str.strip()) + 1
                        break
                    except (ValueError, AttributeError):
                        continue

            new_row = [
                next_id,
                str(employee_id),
                bonus_type,
                f"{value:.2f}",
                "false",
                str(shift_id) if shift_id else "",
                created_at
            ]

            ws.append_row(new_row, value_input_option="RAW")
            logger.info(f"Created bonus {bonus_type} ({value}) for employee {employee_id}, shift {shift_id}")

            return next_id
        except (WorksheetNotFound, APIError) as e:
            logger.error(f"Failed to create bonus: {e}")
            return 0

    def apply_bonus(self, bonus_id: int, shift_id: int) -> None:
        """Mark bonus as applied to a shift.

        Args:
            bonus_id: Bonus ID.
            shift_id: Shift ID.
        """
        try:
            ws = self.spreadsheet.worksheet("ActiveBonuses")
            all_records = ws.get_all_records()

            for idx, record in enumerate(all_records, start=2):
                if record.get("ID") == bonus_id:
                    headers = ws.row_values(1)

                    # Update Applied and Shift ID
                    updates = [
                        ("Applied", "true"),
                        ("Shift ID", str(shift_id)),
                    ]

                    for field, value in updates:
                        if field in headers:
                            col_idx = headers.index(field) + 1
                            col_letter = chr(64 + col_idx)
                            cell_range = f"{col_letter}{idx}"
                            ws.update(values=[[value]], range_name=cell_range, value_input_option="RAW")

                    logger.info(f"Applied bonus {bonus_id} to shift {shift_id}")
                    break

        except (WorksheetNotFound, APIError) as e:
            logger.error(f"Failed to apply bonus: {e}")

    def get_shift_applied_bonuses(self, shift_id: int) -> List[Dict]:
        """Get bonuses that were applied to a specific shift.

        Args:
            shift_id: Shift ID.

        Returns:
            List of bonus dicts that were applied to this shift.
        """
        # Try cache first
        cache_key = str(shift_id)
        cached = self.cache_manager.get("shift_bonuses", cache_key)
        if cached is not None:
            logger.debug(f"✓ Cache HIT: shift_bonuses[{cache_key}]")
            return cached

        logger.debug(f"✗ Cache MISS: shift_bonuses[{cache_key}]")
        try:
            ws = self.spreadsheet.worksheet("ActiveBonuses")
            all_records = ws.get_all_records()

            applied_bonuses = []
            for record in all_records:
                # Check if this bonus was applied to the given shift
                if (str(record.get("Applied")).lower() == "true"
                    and str(record.get("Shift ID")) == str(shift_id)):
                    applied_bonuses.append(record)

            # Cache for 10 minutes
            self.cache_manager.set("shift_bonuses", cache_key, applied_bonuses, ttl=600)

            return applied_bonuses
        except (WorksheetNotFound, APIError) as e:
            logger.error(f"Failed to get shift applied bonuses: {e}")
            return []

    def get_models_from_shift(self, shift: Dict) -> List[str]:
        """Extract model names that have sales > 0 from shift.

        Args:
            shift: Shift record dictionary.

        Returns:
            List of model names (e.g., ['Model A', 'Model B']).
        """
        models = []
        for key, value in shift.items():
            if key in Config.PRODUCTS:
                try:
                    if value and Decimal(str(value)) > 0:
                        models.append(key)
                except (ValueError, TypeError, InvalidOperation):
                    continue
        return models

    def find_previous_shift_with_models(
        self,
        employee_id: int,
        models: List[str],
        before_date: str
    ) -> Optional[Dict]:
        """Find previous shift where another employee sold any of the specified models.

        Args:
            employee_id: Current employee ID (to exclude).
            models: List of model names to search for.
            before_date: Search for shifts before this date (YYYY/MM/DD HH:MM:SS).

        Returns:
            Shift record dictionary or None.
        """
        try:
            ws = self.get_worksheet()
            all_records = ws.get_all_records()

            # Filter and sort shifts
            candidate_shifts = []
            for record in all_records:
                # Skip same employee
                if str(record.get("EmployeeId")) == str(employee_id):
                    continue

                # Check if shift date is before current
                shift_date = str(record.get("Date", ""))
                if shift_date >= before_date:
                    continue

                # Check if any model matches
                has_model = False
                for model in models:
                    if model in record:
                        try:
                            value = Decimal(str(record[model])) if record[model] else Decimal("0")
                            if value > 0:
                                has_model = True
                                break
                        except (ValueError, TypeError, InvalidOperation):
                            continue

                if has_model:
                    candidate_shifts.append(record)

            # Sort by date descending, return most recent
            if candidate_shifts:
                candidate_shifts.sort(key=lambda x: x.get("Date", ""), reverse=True)
                return candidate_shifts[0]

            return None

        except (WorksheetNotFound, APIError) as e:
            logger.error(f"Failed to find previous shift: {e}")
            return None

    def find_shifts_with_model(
        self,
        model: str,
        date: str,
        exclude_employee: int,
        before_time: str
    ) -> List[Dict]:
        """Find all shifts on a specific date where other employees sold a specific model.

        Args:
            model: Model name to search for.
            date: Date to filter by (YYYY/MM/DD HH:MM:SS).
            exclude_employee: Employee ID to exclude.
            before_time: Only include shifts before this time (YYYY/MM/DD HH:MM:SS).

        Returns:
            List of shift records.
        """
        try:
            ws = self.get_worksheet()
            all_records = ws.get_all_records()

            # Extract date part
            date_part = date.split(" ")[0] if " " in date else date

            matching_shifts = []
            for record in all_records:
                # Skip same employee
                if str(record.get("EmployeeId")) == str(exclude_employee):
                    continue

                # Check if same date
                shift_date = str(record.get("Date", ""))
                shift_date_part = shift_date.split(" ")[0] if " " in shift_date else shift_date
                if shift_date_part != date_part:
                    continue

                # Check if before current shift time
                if shift_date >= before_time:
                    continue

                # Check if model has sales
                if model in record:
                    try:
                        value = Decimal(str(record[model])) if record[model] else Decimal("0")
                        if value > 0:
                            matching_shifts.append(record)
                    except (ValueError, TypeError, InvalidOperation):
                        continue

            return matching_shifts

        except (WorksheetNotFound, APIError) as e:
            logger.error(f"Failed to find shifts with model: {e}")
            return []

    def apply_percent_prev_bonus(
        self,
        employee_id: int,
        current_shift: Dict,
        bonus_value: float
    ) -> Decimal:
        """Apply percent_prev bonus: +X% from previous shift chatter.

        Args:
            employee_id: Current employee ID.
            current_shift: Current shift data.
            bonus_value: Bonus percentage (e.g., 1.0 for 1%).

        Returns:
            Bonus amount in $.
        """
        try:
            import random

            # 1. Get models from current shift
            current_models = self.get_models_from_shift(current_shift)
            if not current_models:
                logger.info("No models in current shift for percent_prev bonus")
                return Decimal("0")

            # 2. Find previous shift with these models
            prev_shift = self.find_previous_shift_with_models(
                employee_id=employee_id,
                models=current_models,
                before_date=current_shift.get("Date", "")
            )

            if not prev_shift:
                logger.info("No previous shift found for percent_prev bonus")
                return Decimal("0")

            # 3. Get models from previous shift
            prev_models = self.get_models_from_shift(prev_shift)

            # 4. Find common models
            common_models = list(set(current_models) & set(prev_models))
            if not common_models:
                logger.info("No common models for percent_prev bonus")
                return Decimal("0")

            # 5. Select random model
            selected_model = random.choice(common_models)
            logger.info(f"Selected model for percent_prev bonus: {selected_model}")

            # 6. Calculate Net sales for model
            model_total_sales = Decimal(str(prev_shift.get(selected_model, 0)))
            model_net_sales = model_total_sales * Decimal("0.8")

            # 7. Calculate bonus
            bonus_amount = model_net_sales * (Decimal(str(bonus_value)) / Decimal("100"))

            logger.info(f"percent_prev bonus calculated: ${bonus_amount:.2f} "
                       f"(model: {selected_model}, net sales: ${model_net_sales:.2f})")

            return bonus_amount

        except Exception as e:
            logger.error(f"Failed to apply percent_prev bonus: {e}")
            return Decimal("0")

    def apply_percent_all_bonus(
        self,
        employee_id: int,
        current_shift: Dict,
        bonus_value: float
    ) -> Decimal:
        """Apply percent_all bonus: +X% from all other chatters on model that day.

        Args:
            employee_id: Current employee ID.
            current_shift: Current shift data.
            bonus_value: Bonus percentage (e.g., 2.0 for 2%).

        Returns:
            Bonus amount in $.
        """
        try:
            import random

            # 1. Get models from current shift
            current_models = self.get_models_from_shift(current_shift)
            if not current_models:
                logger.info("No models in current shift for percent_all bonus")
                return Decimal("0")

            # 2. Select random model
            selected_model = random.choice(current_models)
            logger.info(f"Selected model for percent_all bonus: {selected_model}")

            # 3. Find all shifts with this model today
            other_shifts = self.find_shifts_with_model(
                model=selected_model,
                date=current_shift.get("Date", ""),
                exclude_employee=employee_id,
                before_time=current_shift.get("Clock in", "")
            )

            if not other_shifts:
                logger.info("No other shifts found for percent_all bonus")
                return Decimal("0")

            # 4. Calculate total Net sales
            total_net_sales = Decimal("0")
            for shift in other_shifts:
                model_sales = Decimal(str(shift.get(selected_model, 0)))
                model_net_sales = model_sales * Decimal("0.8")
                total_net_sales += model_net_sales

            # 5. Calculate bonus
            bonus_amount = total_net_sales * (Decimal(str(bonus_value)) / Decimal("100"))

            logger.info(f"percent_all bonus calculated: ${bonus_amount:.2f} "
                       f"(model: {selected_model}, {len(other_shifts)} shifts, "
                       f"total net sales: ${total_net_sales:.2f})")

            return bonus_amount

        except Exception as e:
            logger.error(f"Failed to apply percent_all bonus: {e}")
            return Decimal("0")
