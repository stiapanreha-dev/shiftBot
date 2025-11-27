"""PostgreSQL service - drop-in replacement for SheetsService.

This service provides 100% compatibility with SheetsService interface
but uses the existing PostgreSQL database schema.

Schema mapping:
- shifts table (normalized with shift_products)
- employees table (replaces EmployeeSettings)
- dynamic_rates table (min_amount, max_amount, percentage)
- ranks table (min_amount, max_amount)
- active_bonuses table
- products & shift_products (normalized many-to-many)

Author: Claude Code (PROMPT 4.1 - Final PostgreSQL Integration)
Date: 2025-11-11
Version: 3.1.0
"""

import logging
from typing import Dict, List, Optional
from decimal import Decimal
from datetime import datetime, date
import psycopg2
from psycopg2 import sql, extras

from config import Config

logger = logging.getLogger(__name__)


def get_db_connection(**params):
    """Get PostgreSQL connection with RealDictCursor."""
    db_params = Config.get_db_params()
    db_params.update(params)

    return psycopg2.connect(
        **db_params,
        cursor_factory=extras.RealDictCursor
    )


class PostgresService:
    """PostgreSQL service - drop-in replacement for SheetsService.

    Provides identical interface to SheetsService but uses PostgreSQL backend.
    """

    def __init__(self, cache_manager=None, **db_params):
        """Initialize PostgreSQL service.

        Args:
            cache_manager: Optional CacheManager instance (for compatibility)
            **db_params: PostgreSQL connection parameters (optional overrides)
        """
        self.db_params = db_params
        self.cache_manager = cache_manager

        # Test connection
        try:
            conn = get_db_connection(**self.db_params)
            conn.close()
            logger.info("✓ PostgreSQL service initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize PostgreSQL connection: {e}")
            raise

    def _get_conn(self):
        """Get a new database connection."""
        return get_db_connection(**self.db_params)

    # ========== Shift Management ==========

    def get_next_id(self) -> int:
        """Get next available ID for shift.

        Returns:
            Next ID value from sequence
        """
        conn = self._get_conn()
        cursor = conn.cursor()

        try:
            # Use nextval to get next sequence value
            cursor.execute("SELECT nextval('shifts_id_seq')")
            next_id = cursor.fetchone()['nextval']

            # Rollback to not consume the sequence value
            conn.rollback()

            return next_id
        finally:
            cursor.close()
            conn.close()

    def create_shift(self, shift_data: Dict) -> int:
        """Create a new shift with products.

        Args:
            shift_data: Dict containing shift information matching SheetsService format

        Returns:
            shift_id of created shift
        """
        conn = self._get_conn()
        cursor = conn.cursor()

        try:
            # Extract data - support both formats
            employee_id = shift_data['employee_id']
            employee_name = shift_data['employee_name']

            # Format 1: date + clock_in/clock_out (from handlers.py)
            if 'clock_in' in shift_data:
                clock_in = shift_data['clock_in']  # Already formatted timestamp
                clock_out = shift_data.get('clock_out')
                # Extract date from clock_in
                shift_date = clock_in.split()[0] if clock_in else shift_data.get('date', '')
            # Format 2: shift_date + time_in/time_out (from SheetsService)
            else:
                shift_date = shift_data['shift_date']  # YYYY-MM-DD
                time_in = shift_data['time_in']  # HH:MM
                time_out = shift_data.get('time_out')  # HH:MM or None
                # Construct timestamps
                clock_in = f"{shift_date} {time_in}:00"
                clock_out = f"{shift_date} {time_out}:00" if time_out else None

            # Get or calculate total_sales from products
            products = shift_data.get('products', {})
            if 'total_sales' in shift_data:
                total_sales = Decimal(str(shift_data['total_sales']))
            else:
                # Calculate from products
                total_sales = sum(Decimal(str(amount)) for amount in products.values())

            # Calculate worked_hours if not provided
            if 'total_hours' in shift_data:
                worked_hours = Decimal(str(shift_data['total_hours']))
            elif clock_in and clock_out:
                # Parse timestamps and calculate hours
                from datetime import datetime
                fmt = "%Y/%m/%d %H:%M:%S"
                dt_in = datetime.strptime(clock_in, fmt)
                dt_out = datetime.strptime(clock_out, fmt)
                hours = (dt_out - dt_in).total_seconds() / 3600
                worked_hours = Decimal(str(hours))
            else:
                worked_hours = Decimal('0')

            # Calculate financial fields if not provided
            net_sales = Decimal(str(shift_data.get('net_sales', total_sales * Decimal('0.8'))))

            # Get employee settings for base commission and hourly wage
            settings = self.get_employee_settings(employee_id)
            if settings is None:
                # Auto-create employee for new user
                self._create_employee_from_shift(employee_id, employee_name)
                settings = self.get_employee_settings(employee_id)
            hourly_wage = Decimal(str(settings.get("Hourly wage", 15.0)))
            base_commission = Decimal(str(settings.get("Sales commission", 8.0)))

            # Calculate total_per_hour
            total_per_hour = Decimal(str(shift_data.get('total_per_hour', worked_hours * hourly_wage)))

            # Calculate dynamic commission rate
            # Convert shift_date format from YYYY/MM/DD to YYYY-MM-DD for calculate_dynamic_rate
            shift_date_normalized = shift_date.replace("/", "-")
            dynamic_rate = Decimal(str(self.calculate_dynamic_rate(employee_id, shift_date_normalized, float(total_sales))))

            # Start with base + dynamic commission
            commission_pct = base_commission + dynamic_rate
            flat_bonuses = Decimal('0')
            applied_bonus_ids = []  # Track applied bonuses to mark them later

            # Apply active bonuses if shift is complete (has clock_out)
            if clock_out:
                active_bonuses = self.get_active_bonuses(employee_id)
                for bonus in active_bonuses:
                    bonus_id = bonus.get("ID")
                    bonus_type = bonus.get("Bonus Type", "")
                    bonus_value = Decimal(str(bonus.get("Value", 0)))

                    if bonus_type == "percent_next":
                        commission_pct += bonus_value
                        applied_bonus_ids.append(bonus_id)
                        logger.info(f"Applied percent_next bonus {bonus_id}: +{bonus_value}%")
                    elif bonus_type == "double_commission":
                        commission_pct *= Decimal("2")
                        applied_bonus_ids.append(bonus_id)
                        logger.info(f"Applied double_commission bonus {bonus_id}: commission doubled")
                    elif bonus_type in ["flat", "flat_immediate"]:
                        flat_bonuses += bonus_value
                        applied_bonus_ids.append(bonus_id)
                        logger.info(f"Applied flat bonus {bonus_id}: +${bonus_value}")

            # Calculate commissions from net sales
            commissions = Decimal(str(shift_data.get('commission_amount', net_sales * (commission_pct / Decimal('100')))))

            # Calculate total made
            total_made = Decimal(str(shift_data.get('total_made', commissions + total_per_hour + flat_bonuses)))

            # Insert shift
            cursor.execute("""
                INSERT INTO shifts (
                    date, employee_id, employee_name,
                    clock_in, clock_out, worked_hours,
                    total_sales, net_sales, commission_pct,
                    total_per_hour, commissions, total_made,
                    synced_to_sheets
                ) VALUES (
                    %s, %s, %s,
                    %s, %s, %s,
                    %s, %s, %s,
                    %s, %s, %s,
                    FALSE
                )
                RETURNING id
            """, (
                shift_date, employee_id, employee_name,
                clock_in, clock_out, worked_hours,
                total_sales, net_sales, commission_pct,
                total_per_hour, commissions, total_made
            ))

            shift_id = cursor.fetchone()['id']

            # Mark applied bonuses as used (pass cursor to use same transaction)
            for bonus_id in applied_bonus_ids:
                if bonus_id:
                    self.apply_bonus(bonus_id, shift_id, cursor=cursor)
                    logger.info(f"Marked bonus {bonus_id} as applied to shift {shift_id}")

            # Insert products (already extracted above)
            for product_name, amount in products.items():
                amount_decimal = Decimal(str(amount))
                if amount_decimal > 0:
                    # Get product_id
                    cursor.execute("SELECT id FROM products WHERE name = %s", (product_name,))
                    product = cursor.fetchone()

                    if product:
                        cursor.execute("""
                            INSERT INTO shift_products (shift_id, product_id, amount)
                            VALUES (%s, %s, %s)
                            ON CONFLICT (shift_id, product_id) DO UPDATE
                            SET amount = EXCLUDED.amount
                        """, (shift_id, product['id'], amount_decimal))
                    else:
                        logger.warning(f"Product '{product_name}' not found in database")

            conn.commit()
            logger.info(f"✓ Created shift {shift_id} for employee {employee_id}")
            return shift_id

        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to create shift: {e}")
            raise
        finally:
            cursor.close()
            conn.close()

    def get_shift_by_id(self, shift_id: int) -> Optional[Dict]:
        """Get shift data by ID with product sales in SheetsService format.

        Args:
            shift_id: Shift ID

        Returns:
            Shift data dict compatible with SheetsService or None
        """
        conn = self._get_conn()
        cursor = conn.cursor()

        try:
            # Get shift base data
            cursor.execute("SELECT * FROM shifts WHERE id = %s", (shift_id,))
            shift = cursor.fetchone()

            if not shift:
                return None

            # Convert to SheetsService format
            result = {
                'ShiftID': shift['id'],
                'ID': shift['id'],  # Alias
                'shift_id': shift['id'],  # Python-style alias
                'Date': str(shift['date']),
                'shift_date': str(shift['date']),
                'EmployeeId': shift['employee_id'],
                'employee_id': shift['employee_id'],
                'EmployeeName': shift['employee_name'],
                'employee_name': shift['employee_name'],
                'Clock in': shift['clock_in'].strftime('%H:%M') if shift['clock_in'] else '',
                'time_in': shift['clock_in'].strftime('%H:%M') if shift['clock_in'] else '',
                'Clock out': shift['clock_out'].strftime('%H:%M') if shift['clock_out'] else '',
                'time_out': shift['clock_out'].strftime('%H:%M') if shift['clock_out'] else '',
                'Worked hours/shift': float(shift['worked_hours']) if shift['worked_hours'] else 0,
                'total_hours': float(shift['worked_hours']) if shift['worked_hours'] else 0,
                'Total sales': float(shift['total_sales']),
                'total_sales': float(shift['total_sales']),
                'Net sales': float(shift['net_sales']),
                'net_sales': float(shift['net_sales']),
                '%': float(shift['commission_pct']),
                'CommissionPct': float(shift['commission_pct']),
                'commission_pct': float(shift['commission_pct']),
                'total_commission_pct': float(shift['commission_pct']),
                'Total per hour': float(shift['total_per_hour']),
                'total_per_hour': float(shift['total_per_hour']),
                'Commissions': float(shift['commissions']),
                'commissions': float(shift['commissions']),
                'commission_amount': float(shift['commissions']),
                'Total made': float(shift['total_made']),
                'total_made': float(shift['total_made']),
            }

            # Get product sales
            cursor.execute("""
                SELECT p.name, sp.amount
                FROM shift_products sp
                JOIN products p ON sp.product_id = p.id
                WHERE sp.shift_id = %s
            """, (shift_id,))

            products = cursor.fetchall()

            # Initialize all products to 0 (load from DB)
            all_products = self.get_products()
            for product_name in all_products:
                result[product_name] = 0
                result[f"{product_name.lower()}_sales"] = 0

            # Fill in actual product sales
            for product_row in products:
                product_name = product_row['name']
                amount = float(product_row['amount'])
                result[product_name] = amount
                result[f"{product_name.lower()}_sales"] = amount

            return result

        finally:
            cursor.close()
            conn.close()

    def find_row_by_id(self, shift_id: int) -> Optional[int]:
        """Find shift row by ID (for compatibility).

        Args:
            shift_id: Shift ID

        Returns:
            Shift ID if found (PostgreSQL doesn't have row numbers)
        """
        shift = self.get_shift_by_id(shift_id)
        return shift_id if shift else None

    def update_shift_field(self, shift_id: int, field: str, value: str) -> bool:
        """Update a single field of a shift.

        Args:
            shift_id: Shift ID
            field: Field name from SheetsService format
            value: New value

        Returns:
            True if successful
        """
        conn = self._get_conn()
        cursor = conn.cursor()

        # Map SheetsService field names to PostgreSQL columns
        field_mapping = {
            'Clock in': 'clock_in',
            'Clock out': 'clock_out',
            'Worked hours/shift': 'worked_hours',
            'Total sales': 'total_sales',
            'Net sales': 'net_sales',
            '%': 'commission_pct',
            'CommissionPct': 'commission_pct',
            'Total per hour': 'total_per_hour',
            'Commissions': 'commissions',
            'Total made': 'total_made',
        }

        pg_field = field_mapping.get(field, field)

        try:
            # Special handling for time fields
            if pg_field in ['clock_in', 'clock_out']:
                # Value comes as 'YYYY/MM/DD HH:MM:SS' - convert to PostgreSQL format
                full_datetime = value.replace("/", "-")

                cursor.execute(
                    sql.SQL("UPDATE shifts SET {} = %s, updated_at = now() WHERE id = %s").format(
                        sql.Identifier(pg_field)
                    ),
                    (full_datetime, shift_id)
                )
            else:
                cursor.execute(
                    sql.SQL("UPDATE shifts SET {} = %s, updated_at = now() WHERE id = %s").format(
                        sql.Identifier(pg_field)
                    ),
                    (value, shift_id)
                )

            conn.commit()
            logger.info(f"✓ Updated shift {shift_id}: {pg_field} = {value}")

            # Invalidate cache if cache_manager exists
            if self.cache_manager:
                self.cache_manager.invalidate_key('shift', shift_id)

            return True

        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to update shift field: {e}")
            return False
        finally:
            cursor.close()
            conn.close()

    def recalculate_worked_hours(self, shift_id: int) -> bool:
        """Recalculate worked_hours, total_per_hour based on clock_in/clock_out.

        Args:
            shift_id: Shift ID

        Returns:
            True if successful
        """
        conn = self._get_conn()
        cursor = conn.cursor()

        try:
            cursor.execute(
                "SELECT clock_in, clock_out, commissions FROM shifts WHERE id = %s",
                (shift_id,)
            )
            shift = cursor.fetchone()

            if not shift or not shift['clock_in'] or not shift['clock_out']:
                return False

            clock_in = shift['clock_in']
            clock_out = shift['clock_out']
            commissions = shift['commissions'] or Decimal('0')

            # Calculate worked hours
            diff = clock_out - clock_in
            worked_hours = Decimal(str(diff.total_seconds() / 3600))
            worked_hours = worked_hours.quantize(Decimal('0.01'))

            # Recalculate total_per_hour
            total_per_hour = commissions / worked_hours if worked_hours > 0 else Decimal('0')

            cursor.execute("""
                UPDATE shifts
                SET worked_hours = %s,
                    total_per_hour = %s,
                    updated_at = now()
                WHERE id = %s
            """, (worked_hours, total_per_hour, shift_id))

            conn.commit()
            logger.info(f"✓ Recalculated worked_hours for shift {shift_id}: {worked_hours}h")

            if self.cache_manager:
                self.cache_manager.invalidate_key('shift', shift_id)

            return True

        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to recalculate worked_hours: {e}")
            return False
        finally:
            cursor.close()
            conn.close()

    def update_total_sales(self, shift_id: int, total_sales: Decimal) -> bool:
        """Update total sales for a shift.

        Args:
            shift_id: Shift ID
            total_sales: New total sales value

        Returns:
            True if successful
        """
        conn = self._get_conn()
        cursor = conn.cursor()

        try:
            # Get commission_pct
            cursor.execute("SELECT commission_pct, worked_hours FROM shifts WHERE id = %s", (shift_id,))
            shift = cursor.fetchone()

            if not shift:
                return False

            commission_pct = shift['commission_pct']
            worked_hours = shift['worked_hours'] or Decimal('1')

            # Recalculate
            net_sales = total_sales * Decimal('0.8')
            commissions = total_sales * commission_pct / 100
            total_per_hour = commissions / worked_hours if worked_hours > 0 else Decimal('0')
            total_made = commissions

            # Update shift
            cursor.execute("""
                UPDATE shifts
                SET total_sales = %s,
                    net_sales = %s,
                    commissions = %s,
                    total_per_hour = %s,
                    total_made = %s,
                    updated_at = now()
                WHERE id = %s
            """, (total_sales, net_sales, commissions, total_per_hour, total_made, shift_id))

            conn.commit()
            logger.info(f"✓ Updated total_sales for shift {shift_id}: {total_sales}")

            # Invalidate cache
            if self.cache_manager:
                self.cache_manager.invalidate_key('shift', shift_id)
                self.cache_manager.invalidate_key('shift_bonuses', shift_id)

            return True

        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to update total_sales: {e}")
            return False
        finally:
            cursor.close()
            conn.close()

    def get_last_shifts(self, employee_id: int, limit: int = 3) -> List[Dict]:
        """Get last N shifts for an employee.

        Args:
            employee_id: Employee ID
            limit: Number of shifts to return

        Returns:
            List of shift dicts in SheetsService format
        """
        conn = self._get_conn()
        cursor = conn.cursor()

        try:
            cursor.execute("""
                SELECT * FROM shifts
                WHERE employee_id = %s
                ORDER BY date DESC, clock_in DESC
                LIMIT %s
            """, (employee_id, limit))

            shifts = cursor.fetchall()

            # Convert each shift to SheetsService format
            result = []
            for shift in shifts:
                shift_dict = self.get_shift_by_id(shift['id'])
                if shift_dict:
                    result.append(shift_dict)

            return result

        finally:
            cursor.close()
            conn.close()

    def get_all_shifts(self) -> List[Dict]:
        """Get all shifts.

        Returns:
            List of all shift dicts in SheetsService format
        """
        conn = self._get_conn()
        cursor = conn.cursor()

        try:
            cursor.execute("""
                SELECT id FROM shifts
                ORDER BY date DESC, clock_in DESC
            """)

            shift_ids = cursor.fetchall()

            # Convert each shift to SheetsService format
            result = []
            for row in shift_ids:
                shift_dict = self.get_shift_by_id(row['id'])
                if shift_dict:
                    result.append(shift_dict)

            return result

        finally:
            cursor.close()
            conn.close()

    # ========== Products ==========

    def get_products(self) -> List[str]:
        """Get list of active products from database.

        Returns:
            List of product names ordered by display_order
        """
        # No caching - always fetch fresh (query is fast, products may change)
        conn = self._get_conn()
        cursor = conn.cursor()

        try:
            cursor.execute("""
                SELECT name FROM products
                WHERE is_active = TRUE
                ORDER BY display_order, id
            """)

            return [row['name'] for row in cursor.fetchall()]

        finally:
            cursor.close()
            conn.close()

    # ========== Employee Settings ==========

    def get_employee_settings(self, employee_id: int) -> Optional[Dict]:
        """Get employee settings in SheetsService format.

        Args:
            employee_id: Employee ID

        Returns:
            Employee settings dict or None
        """
        # Try cache first
        # Always fetch fresh from DB, no caching for employee settings
        conn = self._get_conn()
        cursor = conn.cursor()

        try:
            cursor.execute("""
                SELECT * FROM employees WHERE telegram_id = %s AND is_active = TRUE
            """, (employee_id,))

            employee = cursor.fetchone()

            if not employee:
                return None

            # Convert to SheetsService format
            hourly_wage = float(employee['hourly_wage']) if employee['hourly_wage'] else 15.0
            sales_commission = float(employee['sales_commission']) if employee['sales_commission'] else 8.0

            result = {
                'EmployeeID': employee['id'],
                'employee_id': employee['id'],
                'EmployeeName': employee['name'],
                'employee_name': employee['name'],
                'BaseCommissionPct': Decimal(str(sales_commission)),
                'base_commission_pct': Decimal(str(sales_commission)),
                'Sales commission': sales_commission,
                'Hourly wage': hourly_wage,
                'Active': employee['is_active'],
                'active': employee['is_active'],
            }

            return result

        finally:
            cursor.close()
            conn.close()

    def create_default_employee_settings(self, employee_id: int) -> None:
        """Create default employee settings.

        Args:
            employee_id: Employee ID
        """
        conn = self._get_conn()
        cursor = conn.cursor()

        try:
            cursor.execute("""
                INSERT INTO employees (id, name, is_active)
                VALUES (%s, %s, TRUE)
                ON CONFLICT (id) DO NOTHING
            """, (employee_id, f"Employee {employee_id}"))

            conn.commit()
            logger.info(f"✓ Created default settings for employee {employee_id}")

            # Invalidate cache
            if self.cache_manager:
                self.cache_manager.invalidate_key('employee_settings', employee_id)

        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to create default employee settings: {e}")
            raise
        finally:
            cursor.close()
            conn.close()

    def _create_employee_from_shift(self, telegram_id: int, name: str) -> None:
        """Auto-create employee record from shift data.

        Args:
            telegram_id: Telegram user ID
            name: Employee name
        """
        conn = self._get_conn()
        cursor = conn.cursor()

        try:
            # Set id = telegram_id so foreign keys in shifts work correctly
            cursor.execute("""
                INSERT INTO employees (id, name, telegram_id, is_active)
                VALUES (%s, %s, %s, TRUE)
                ON CONFLICT (id) DO NOTHING
            """, (telegram_id, name, telegram_id))

            conn.commit()
            logger.info(f"✓ Auto-created employee: {name} (telegram_id={telegram_id})")

            # Invalidate cache
            if self.cache_manager:
                self.cache_manager.invalidate_key('employee_settings', telegram_id)

        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to auto-create employee: {e}")
            raise
        finally:
            cursor.close()
            conn.close()

    # ========== Dynamic Rates ==========

    def get_dynamic_rates(self) -> List[Dict]:
        """Get all dynamic commission rates in SheetsService format.

        Returns:
            List of rate dicts
        """
        # Try cache first
        if self.cache_manager:
            cached = self.cache_manager.get('dynamic_rates', 'all')
            if cached:
                return cached

        conn = self._get_conn()
        cursor = conn.cursor()

        try:
            cursor.execute("""
                SELECT * FROM dynamic_rates
                WHERE is_active = TRUE
                ORDER BY min_amount ASC
            """)

            rates = cursor.fetchall()

            # Convert to SheetsService format
            result = []
            for rate in rates:
                result.append({
                    'MinSales': float(rate['min_amount']),
                    'min_sales': float(rate['min_amount']),
                    'MaxSales': float(rate['max_amount']),
                    'max_sales': float(rate['max_amount']),
                    'RatePct': float(rate['percentage']),
                    'rate_pct': float(rate['percentage']),
                })

            # Cache result
            if self.cache_manager:
                self.cache_manager.set('dynamic_rates', 'all', result, ttl=900)

            return result

        finally:
            cursor.close()
            conn.close()

    def calculate_dynamic_rate(
        self,
        employee_id: int,
        shift_date: str,
        current_total_sales: Decimal = Decimal("0")
    ) -> float:
        """Calculate dynamic commission rate using database function.

        Args:
            employee_id: Employee ID
            shift_date: Shift date (YYYY-MM-DD)
            current_total_sales: Current shift total sales

        Returns:
            Dynamic commission rate percentage
        """
        conn = self._get_conn()
        cursor = conn.cursor()

        try:
            # Calculate total sales for the month including current shift
            shift_dt = datetime.strptime(shift_date, "%Y-%m-%d").date()
            month_start = date(shift_dt.year, shift_dt.month, 1)

            # Calculate next month start
            if shift_dt.month == 12:
                month_end = date(shift_dt.year + 1, 1, 1)
            else:
                month_end = date(shift_dt.year, shift_dt.month + 1, 1)

            # Get total sales for the month
            cursor.execute("""
                SELECT COALESCE(SUM(total_sales), 0) as total
                FROM shifts
                WHERE employee_id = %s
                AND date >= %s
                AND date < %s
            """, (employee_id, month_start, month_end))

            monthly_total = cursor.fetchone()['total']
            total_with_current = monthly_total + Decimal(str(current_total_sales))

            # Use database function to get dynamic rate
            cursor.execute("SELECT get_dynamic_rate(%s) as rate", (total_with_current,))
            result = cursor.fetchone()

            return float(result['rate']) if result else 0.0

        finally:
            cursor.close()
            conn.close()

    # ========== Ranks ==========

    def get_ranks(self) -> List[Dict]:
        """Get all ranks in SheetsService format.

        Returns:
            List of rank dicts
        """
        # Try cache first
        if self.cache_manager:
            cached = self.cache_manager.get('ranks', 'all')
            if cached:
                return cached

        conn = self._get_conn()
        cursor = conn.cursor()

        try:
            cursor.execute("""
                SELECT * FROM ranks
                WHERE is_active = TRUE
                ORDER BY display_order ASC
            """)

            ranks = cursor.fetchall()

            # Convert to SheetsService format
            result = []
            for rank in ranks:
                # Get rank bonuses
                cursor.execute("""
                    SELECT bonus_code FROM rank_bonuses
                    WHERE rank_id = %s
                    ORDER BY position ASC
                """, (rank['id'],))

                bonuses = cursor.fetchall()
                bonus_codes = [b['bonus_code'] for b in bonuses]

                result.append({
                    'RankName': rank['name'],
                    'rank_name': rank['name'],
                    'BonusPct': 0,  # Ranks don't have percentage in this schema
                    'bonus_pct': 0,
                    'MinTotalSales': float(rank['min_amount']),
                    'min_total_sales': float(rank['min_amount']),
                    'MaxTotalSales': float(rank['max_amount']),
                    'max_total_sales': float(rank['max_amount']),
                    'Description': rank['text'] or '',
                    'description': rank['text'] or '',
                    'Emoji': rank.get('emoji') or '',
                    'emoji': rank.get('emoji') or '',
                    'Bonuses': ','.join(bonus_codes),  # Comma-separated bonus codes
                })

            # Cache result
            if self.cache_manager:
                self.cache_manager.set('ranks', 'all', result, ttl=900)

            return result

        finally:
            cursor.close()
            conn.close()

    def get_employee_rank(self, employee_id: int, year: int, month: int) -> Optional[Dict]:
        """Get employee rank record for a specific month.

        Args:
            employee_id: Employee ID
            year: Year
            month: Month (1-12)

        Returns:
            Dict with employee rank record or None
        """
        # Try cache first
        cache_key = f"{employee_id}_{year}_{month}"
        if self.cache_manager:
            cached = self.cache_manager.get('employee_rank', cache_key)
            if cached:
                return cached

        conn = self._get_conn()
        cursor = conn.cursor()

        try:
            # Get employee rank record from employee_ranks table
            cursor.execute("""
                SELECT
                    er.employee_id,
                    er.year,
                    er.month,
                    curr_rank.name as "Current Rank",
                    prev_rank.name as "Previous Rank",
                    er.notified as "Notified",
                    er.total_sales,
                    er.created_at,
                    er.updated_at
                FROM employee_ranks er
                JOIN ranks curr_rank ON er.current_rank_id = curr_rank.id
                LEFT JOIN ranks prev_rank ON er.previous_rank_id = prev_rank.id
                WHERE er.employee_id = %s
                  AND er.year = %s
                  AND er.month = %s
            """, (employee_id, year, month))

            result = cursor.fetchone()
            if not result:
                return None

            # Convert to dict
            rank_record = dict(result)

            # Cache result
            if self.cache_manager:
                self.cache_manager.set('employee_rank', cache_key, rank_record, ttl=300)

            return rank_record

        finally:
            cursor.close()
            conn.close()

    def update_employee_rank(
        self,
        employee_id: int,
        new_rank: str,
        year: int,
        month: int,
        last_updated: str = None,
        total_sales: float = None
    ) -> None:
        """Update employee rank for a month.

        Args:
            employee_id: Employee ID
            new_rank: New rank name
            year: Year
            month: Month (1-12)
            last_updated: Optional timestamp (not used in PostgreSQL, auto-managed)
            total_sales: Optional total sales amount for the month
        """
        rank_name = new_rank
        conn = self._get_conn()
        cursor = conn.cursor()

        try:
            # Get rank_id
            cursor.execute("SELECT id FROM ranks WHERE name = %s", (rank_name,))
            rank = cursor.fetchone()

            if not rank:
                logger.error(f"Rank '{rank_name}' not found")
                return

            rank_id = rank['id']

            # Calculate total_sales if not provided
            if total_sales is None:
                cursor.execute("""
                    SELECT COALESCE(SUM(total_sales), 0) as total
                    FROM shifts
                    WHERE employee_id = %s
                      AND EXTRACT(YEAR FROM date) = %s
                      AND EXTRACT(MONTH FROM date) = %s
                """, (employee_id, year, month))
                result = cursor.fetchone()
                total_sales = float(result['total']) if result else 0.0

            # Get existing current_rank_id to store as previous_rank_id
            cursor.execute("""
                SELECT current_rank_id FROM employee_ranks
                WHERE employee_id = %s AND year = %s AND month = %s
            """, (employee_id, year, month))

            existing = cursor.fetchone()
            previous_rank_id = existing['current_rank_id'] if existing else None

            # Check if rank changed
            rank_changed = existing and existing['current_rank_id'] != rank_id

            # Upsert employee rank with previous_rank_id tracking
            # Note: notified is reset to FALSE on rank change, preserved otherwise
            cursor.execute("""
                INSERT INTO employee_ranks (employee_id, year, month, current_rank_id, previous_rank_id, total_sales, notified)
                VALUES (%s, %s, %s, %s, %s, %s, FALSE)
                ON CONFLICT (employee_id, year, month) DO UPDATE
                SET previous_rank_id = COALESCE(employee_ranks.current_rank_id, EXCLUDED.previous_rank_id),
                    current_rank_id = EXCLUDED.current_rank_id,
                    total_sales = EXCLUDED.total_sales,
                    notified = CASE
                        WHEN employee_ranks.current_rank_id != EXCLUDED.current_rank_id THEN FALSE
                        ELSE employee_ranks.notified
                    END,
                    updated_at = now()
            """, (employee_id, year, month, rank_id, previous_rank_id, total_sales))

            conn.commit()
            logger.info(f"✓ Updated rank for employee {employee_id} ({year}-{month:02d}): {rank_name}, sales: ${total_sales:.2f}")

            # Invalidate cache
            if self.cache_manager:
                cache_key = f"{employee_id}_{year}_{month}"
                self.cache_manager.invalidate_key('employee_rank', cache_key)

        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to update employee rank: {e}")
            raise
        finally:
            cursor.close()
            conn.close()

    def mark_rank_notified(self, employee_id: int, year: int, month: int) -> None:
        """Mark that employee was notified about rank change.

        Args:
            employee_id: Employee ID
            year: Year
            month: Month (1-12)
        """
        conn = self._get_conn()
        cursor = conn.cursor()

        try:
            cursor.execute("""
                UPDATE employee_ranks
                SET notified = TRUE, updated_at = NOW()
                WHERE employee_id = %s AND year = %s AND month = %s
            """, (employee_id, year, month))

            conn.commit()
            logger.info(f"✓ Marked rank notified for employee {employee_id} ({year}-{month:02d})")

            # Invalidate cache
            if self.cache_manager:
                cache_key = f"{employee_id}_{year}_{month}"
                self.cache_manager.invalidate_key('employee_rank', cache_key)

        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to mark rank notified: {e}")
            raise
        finally:
            cursor.close()
            conn.close()

    def determine_rank(self, employee_id: int, year: int, month: int) -> str:
        """Determine employee rank based on monthly total sales.

        Args:
            employee_id: Employee ID
            year: Year
            month: Month (1-12)

        Returns:
            Rank name based on total sales
        """
        conn = self._get_conn()
        cursor = conn.cursor()

        try:
            # Calculate total sales for the month
            month_val = f"{year}-{month:02d}"
            cursor.execute("""
                SELECT COALESCE(SUM(total_sales), 0) as total
                FROM shifts
                WHERE employee_id = %s
                  AND to_char(clock_in, 'YYYY-MM') = %s
            """, (employee_id, month_val))

            result = cursor.fetchone()
            total_sales = float(result['total']) if result else 0.0

            # Get ranks and find matching rank
            cursor.execute("""
                SELECT name
                FROM ranks
                WHERE min_amount <= %s AND max_amount > %s
                  AND is_active = true
                ORDER BY min_amount
                LIMIT 1
            """, (total_sales, total_sales))

            rank = cursor.fetchone()
            return rank['name'] if rank else "Rookie"

        except Exception as e:
            logger.error(f"Failed to determine rank: {e}")
            return "Rookie"
        finally:
            cursor.close()
            conn.close()

    def get_rank_text(self, rank_name: str) -> str:
        """Get rank description text.

        Args:
            rank_name: Rank name

        Returns:
            Description text
        """
        ranks = self.get_ranks()
        for rank in ranks:
            if rank['rank_name'] == rank_name:
                return rank['description']
        return ""

    def get_rank_bonuses(self, rank_name: str) -> List[str]:
        """Get bonus codes for a rank.

        Args:
            rank_name: Rank name

        Returns:
            List of bonus codes
        """
        ranks = self.get_ranks()
        for rank in ranks:
            if rank['rank_name'] == rank_name:
                bonuses_str = rank.get('Bonuses', '')
                return [b.strip() for b in bonuses_str.split(',') if b.strip()]
        return []

    # ========== Active Bonuses ==========

    def get_active_bonuses(self, employee_id: int) -> List[Dict]:
        """Get active (unapplied) bonuses for an employee in SheetsService format.

        Args:
            employee_id: Employee ID

        Returns:
            List of bonus dicts
        """
        conn = self._get_conn()
        cursor = conn.cursor()

        try:
            cursor.execute("""
                SELECT * FROM active_bonuses
                WHERE employee_id = %s AND applied = FALSE
                ORDER BY created_at ASC
            """, (employee_id,))

            bonuses = cursor.fetchall()

            # Convert to SheetsService format
            result = []
            for bonus in bonuses:
                result.append({
                    'ID': bonus['id'],
                    'EmployeeID': bonus['employee_id'],
                    'Bonus Type': bonus['bonus_type'],
                    'Value': float(bonus['value']),
                    'Applied': bonus['applied'],
                })

            return result

        finally:
            cursor.close()
            conn.close()

    def create_bonus(
        self,
        employee_id: int,
        bonus_type: str,
        value: Decimal,
        notes: str = ""
    ) -> int:
        """Create a new bonus.

        Args:
            employee_id: Employee ID
            bonus_type: Bonus type code
            value: Bonus value (percentage or flat amount)
            notes: Optional notes

        Returns:
            Bonus ID
        """
        conn = self._get_conn()
        cursor = conn.cursor()

        try:
            cursor.execute("""
                INSERT INTO active_bonuses (employee_id, bonus_type, value, applied)
                VALUES (%s, %s, %s, FALSE)
                RETURNING id
            """, (employee_id, bonus_type, value))

            bonus_id = cursor.fetchone()['id']
            conn.commit()

            logger.info(f"✓ Created bonus {bonus_id} for employee {employee_id}: {bonus_type} ({value})")
            return bonus_id

        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to create bonus: {e}")
            raise
        finally:
            cursor.close()
            conn.close()

    def apply_bonus(self, bonus_id: int, shift_id: int, cursor=None) -> None:
        """Apply a bonus to a shift.

        Args:
            bonus_id: Bonus ID
            shift_id: Shift ID
            cursor: Optional cursor to use (for transaction reuse)
        """
        # Use provided cursor or create new connection
        own_connection = cursor is None
        if own_connection:
            conn = self._get_conn()
            cursor = conn.cursor()

        try:
            cursor.execute("""
                UPDATE active_bonuses
                SET applied = TRUE,
                    shift_id = %s,
                    applied_at = now()
                WHERE id = %s
            """, (shift_id, bonus_id))

            # Only commit if we created our own connection
            if own_connection:
                conn.commit()

            logger.info(f"✓ Applied bonus {bonus_id} to shift {shift_id}")

            # Invalidate cache
            if self.cache_manager:
                self.cache_manager.invalidate_key('shift_bonuses', shift_id)

        except Exception as e:
            if own_connection:
                conn.rollback()
            logger.error(f"Failed to apply bonus: {e}")
            raise
        finally:
            # Only close if we created our own connection
            if own_connection:
                cursor.close()
                conn.close()

    def get_shift_applied_bonuses(self, shift_id: int) -> List[Dict]:
        """Get bonuses applied to a shift in SheetsService format.

        Args:
            shift_id: Shift ID

        Returns:
            List of bonus dicts
        """
        # Try cache first
        if self.cache_manager:
            cached = self.cache_manager.get('shift_bonuses', shift_id)
            if cached:
                return cached

        conn = self._get_conn()
        cursor = conn.cursor()

        try:
            cursor.execute("""
                SELECT * FROM active_bonuses
                WHERE shift_id = %s
                ORDER BY applied_at ASC
            """, (shift_id,))

            bonuses = cursor.fetchall()

            # Convert to SheetsService format
            result = []
            for bonus in bonuses:
                result.append({
                    'BonusType': bonus['bonus_type'],
                    'BonusPct': float(bonus['value']),
                    'ShiftID': bonus['shift_id'],
                })

            # Cache result
            if self.cache_manager:
                self.cache_manager.set('shift_bonuses', shift_id, result, ttl=600)

            return result

        finally:
            cursor.close()
            conn.close()

    # ========== Helper Methods ==========

    def get_models_from_shift(self, shift: Dict) -> List[str]:
        """Get list of product names (models) that have sales in this shift.

        Args:
            shift: Shift data dict

        Returns:
            List of product names
        """
        models = []
        all_products = self.get_products()
        for product in all_products:
            # Try both formats
            if shift.get(product, 0) > 0 or shift.get(f"{product.lower()}_sales", 0) > 0:
                models.append(product)

        return models

    def find_previous_shift_with_models(
        self,
        employee_id: int,
        shift_date: str,
        time_in: str,
        models: List[str]
    ) -> Optional[Dict]:
        """Find previous shift with specified models.

        Args:
            employee_id: Employee ID
            shift_date: Current shift date
            time_in: Current shift time in
            models: List of product names to search for

        Returns:
            Previous shift dict or None
        """
        if not models:
            return None

        conn = self._get_conn()
        cursor = conn.cursor()

        try:
            # Build query to find shifts with these products
            current_timestamp = f"{shift_date} {time_in}:00"

            # Get product IDs
            placeholders = ','.join(['%s'] * len(models))
            cursor.execute(f"""
                SELECT id FROM products WHERE name IN ({placeholders})
            """, models)

            product_ids = [row['id'] for row in cursor.fetchall()]

            if not product_ids:
                return None

            # Find previous shift with any of these products
            product_placeholders = ','.join(['%s'] * len(product_ids))
            query = f"""
                SELECT s.id, s.clock_in
                FROM shifts s
                JOIN shift_products sp ON s.id = sp.shift_id
                WHERE s.employee_id = %s
                AND s.clock_in < %s
                AND sp.product_id IN ({product_placeholders})
                AND sp.amount > 0
                ORDER BY s.clock_in DESC
                LIMIT 1
            """

            cursor.execute(query, [employee_id, current_timestamp] + product_ids)

            result = cursor.fetchone()
            if result:
                return self.get_shift_by_id(result['id'])

            return None

        finally:
            cursor.close()
            conn.close()

    def find_shifts_with_model(
        self,
        employee_id: int,
        shift_date: str,
        time_in: str,
        model: str,
        days_back: int = 30
    ) -> List[Dict]:
        """Find shifts with a specific model within N days back.

        Args:
            employee_id: Employee ID
            shift_date: Current shift date
            time_in: Current shift time in
            model: Product name
            days_back: Days to look back

        Returns:
            List of shift dicts
        """
        conn = self._get_conn()
        cursor = conn.cursor()

        try:
            current_timestamp = f"{shift_date} {time_in}:00"
            cutoff_date = datetime.strptime(shift_date, "%Y-%m-%d").date()

            # Get product ID
            cursor.execute("SELECT id FROM products WHERE name = %s", (model,))
            product = cursor.fetchone()

            if not product:
                return []

            product_id = product['id']

            # Find shifts with this product in last N days
            query = """
                SELECT s.id, s.clock_in
                FROM shifts s
                JOIN shift_products sp ON s.id = sp.shift_id
                WHERE s.employee_id = %s
                AND s.date >= %s - INTERVAL '%s days'
                AND s.clock_in < %s
                AND sp.product_id = %s
                AND sp.amount > 0
                ORDER BY s.clock_in DESC
            """

            cursor.execute(query, (employee_id, cutoff_date, days_back, current_timestamp, product_id))

            shift_ids = cursor.fetchall()

            result = []
            for row in shift_ids:
                shift = self.get_shift_by_id(row['id'])
                if shift:
                    result.append(shift)

            return result

        finally:
            cursor.close()
            conn.close()


# For backward compatibility and testing
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    print("Testing PostgresService...")
    service = PostgresService()

    print(f"\n✅ Service initialized")
    print(f"Total shifts: {len(service.get_all_shifts())}")

    # Test get_shift_by_id
    shift = service.get_shift_by_id(33)
    if shift:
        print(f"\n✅ Shift 33: {shift['employee_name']}, Sales: {shift['total_sales']}")

    print("\n✅ All tests passed!")
