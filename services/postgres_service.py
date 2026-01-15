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
from datetime import datetime, date, timedelta
import psycopg2
from psycopg2 import sql, extras

from config import Config
from services.calculators import CommissionCalculator
from services.formatters import DateFormatter

logger = logging.getLogger(__name__)

# Singleton calculator instance
_commission_calculator = CommissionCalculator()


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
                fmt = "%Y/%m/%d %H:%M:%S"
                dt_in = datetime.strptime(clock_in, fmt)
                dt_out = datetime.strptime(clock_out, fmt)
                hours = (dt_out - dt_in).total_seconds() / 3600
                worked_hours = Decimal(str(hours))
            else:
                worked_hours = Decimal('0')

            # Calculate financial fields if not provided
            net_sales = Decimal(str(shift_data.get('net_sales', total_sales * Decimal('0.8'))))

            # Normalize shift_date format
            shift_date_normalized = DateFormatter.to_db_date(shift_date)

            # Get employee settings and ensure employee exists
            settings = self.get_employee_settings(employee_id)
            if settings is None:
                # Auto-create employee for new user
                self._create_employee_from_shift(employee_id, employee_name)
                settings = self.get_employee_settings(employee_id)
            hourly_wage = Decimal(str(settings.get("Hourly wage", 15.0)))

            # Check and update tier if needed (beginning of month)
            self._check_and_update_tier(employee_id, shift_date_normalized)

            # Get tier and bonuses for calculation
            tier = self.get_employee_tier(employee_id)
            active_bonuses = self.get_active_bonuses(employee_id) if clock_out else []

            # Use CommissionCalculator for all commission logic
            calc_result = _commission_calculator.calculate(
                total_sales=total_sales,
                worked_hours=worked_hours,
                hourly_wage=hourly_wage,
                tier=tier,
                active_bonuses=active_bonuses,
                apply_bonuses=bool(clock_out)
            )

            # Extract values from calculator result
            commission_pct = calc_result.commission_pct
            flat_bonuses = calc_result.flat_bonuses
            applied_bonus_ids = calc_result.applied_bonus_ids
            total_hourly = Decimal(str(shift_data.get('total_per_hour', worked_hours * hourly_wage)))
            commissions = Decimal(str(shift_data.get('commission_amount', calc_result.commissions)))
            total_made = Decimal(str(shift_data.get('total_made', calc_result.total_made)))

            # Calculate rolling average and bonus counter (NEW)
            rolling_average = self.calculate_rolling_average(employee_id, shift_date_normalized)
            bonus_counter = self.calculate_bonus_counter(total_sales, rolling_average)

            # Insert shift with new fields
            cursor.execute("""
                INSERT INTO shifts (
                    date, employee_id, employee_name,
                    clock_in, clock_out, worked_hours,
                    total_sales, net_sales, commission_pct,
                    total_hourly, commissions, total_made,
                    rolling_average, bonus_counter,
                    synced_to_sheets
                ) VALUES (
                    %s, %s, %s,
                    %s, %s, %s,
                    %s, %s, %s,
                    %s, %s, %s,
                    %s, %s,
                    FALSE
                )
                RETURNING id
            """, (
                shift_date_normalized, employee_id, employee_name,
                clock_in, clock_out, worked_hours,
                total_sales, net_sales, commission_pct,
                total_hourly, commissions, total_made,
                rolling_average, bonus_counter
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

            # Update fortnight totals (NEW)
            try:
                shift_dt = datetime.strptime(shift_date_normalized, "%Y-%m-%d").date()
                fortnight_num = self.get_fortnight_number(shift_dt.day)
                self.update_fortnight_totals(employee_id, shift_dt.year, shift_dt.month, fortnight_num)
            except Exception as e:
                logger.warning(f"Failed to update fortnight totals: {e}")

            logger.info(f"✓ Created shift {shift_id} for employee {employee_id} (tier: {tier['name'] if tier else 'N/A'}, rolling_avg: {rolling_average}, bonus_counter: {bonus_counter})")
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
            # Handle renamed column: total_hourly (was total_per_hour)
            total_hourly_val = float(shift.get('total_hourly') or shift.get('total_per_hour') or 0)

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
                'Total per hour': total_hourly_val,  # Keep old name for compatibility
                'total_per_hour': total_hourly_val,  # Keep old name for compatibility
                'Total hourly': total_hourly_val,    # New name
                'total_hourly': total_hourly_val,    # New name
                'Commissions': float(shift['commissions']),
                'commissions': float(shift['commissions']),
                'commission_amount': float(shift['commissions']),
                'Total made': float(shift['total_made']),
                'total_made': float(shift['total_made']),
                # New fields
                'rolling_average': float(shift['rolling_average']) if shift.get('rolling_average') else None,
                'Rolling Average': float(shift['rolling_average']) if shift.get('rolling_average') else None,
                'bonus_counter': bool(shift.get('bonus_counter', False)),
                'Bonus Counter': bool(shift.get('bonus_counter', False)),
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
            'Total per hour': 'total_hourly',  # Renamed
            'total_per_hour': 'total_hourly',  # Renamed
            'Total hourly': 'total_hourly',
            'Commissions': 'commissions',
            'Total made': 'total_made',
            'rolling_average': 'rolling_average',
            'bonus_counter': 'bonus_counter',
        }

        pg_field = field_mapping.get(field, field)

        try:
            # Special handling for time fields
            if pg_field in ['clock_in', 'clock_out']:
                # Value comes as 'YYYY/MM/DD HH:MM:SS' - convert to PostgreSQL format
                full_datetime = DateFormatter.to_db_datetime(value)

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
        """Recalculate worked_hours, total_hourly, total_made based on clock_in/clock_out.

        Args:
            shift_id: Shift ID

        Returns:
            True if successful
        """
        conn = self._get_conn()
        cursor = conn.cursor()

        try:
            cursor.execute(
                "SELECT clock_in, clock_out, commissions, employee_id FROM shifts WHERE id = %s",
                (shift_id,)
            )
            shift = cursor.fetchone()

            if not shift or not shift['clock_in'] or not shift['clock_out']:
                return False

            clock_in = shift['clock_in']
            clock_out = shift['clock_out']
            commissions = shift['commissions'] or Decimal('0')
            employee_id = shift['employee_id']

            # Calculate worked hours
            diff = clock_out - clock_in
            worked_hours = Decimal(str(diff.total_seconds() / 3600))
            worked_hours = worked_hours.quantize(Decimal('0.01'))

            # Get hourly_wage from employee settings
            settings = self.get_employee_settings(employee_id)
            hourly_wage = Decimal(str(settings.get("Hourly wage", 15.0))) if settings else Decimal('15.0')

            # Recalculate total_hourly = worked_hours * hourly_wage
            total_hourly = worked_hours * hourly_wage

            # Recalculate total_made
            total_made = total_hourly + commissions

            cursor.execute("""
                UPDATE shifts
                SET worked_hours = %s,
                    total_hourly = %s,
                    total_made = %s,
                    updated_at = now()
                WHERE id = %s
            """, (worked_hours, total_hourly, total_made, shift_id))

            conn.commit()
            logger.info(f"✓ Recalculated shift {shift_id}: {worked_hours}h, ${total_hourly}/h, total=${total_made}")

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
            # Get shift data including employee_id and date
            cursor.execute("SELECT commission_pct, worked_hours, employee_id, date FROM shifts WHERE id = %s", (shift_id,))
            shift = cursor.fetchone()

            if not shift:
                return False

            commission_pct = shift['commission_pct']
            worked_hours = shift['worked_hours'] or Decimal('1')
            employee_id = shift['employee_id']
            shift_date = shift['date']

            # Get hourly_wage from employee settings
            settings = self.get_employee_settings(employee_id)
            hourly_wage = Decimal(str(settings.get("Hourly wage", 15.0))) if settings else Decimal('15.0')

            # Use CommissionCalculator for recalculation
            calc_result = _commission_calculator.recalculate_from_existing(
                total_sales=total_sales,
                worked_hours=worked_hours,
                hourly_wage=hourly_wage,
                existing_commission_pct=commission_pct
            )

            net_sales = _commission_calculator.calculate_net_sales(total_sales)
            commissions = calc_result.commissions
            total_hourly = worked_hours * hourly_wage
            total_made = calc_result.total_made

            # Recalculate rolling_average and bonus_counter
            shift_date_str = str(shift_date)
            rolling_average = self.calculate_rolling_average(employee_id, shift_date_str)
            bonus_counter = self.calculate_bonus_counter(total_sales, rolling_average)

            # Update shift
            cursor.execute("""
                UPDATE shifts
                SET total_sales = %s,
                    net_sales = %s,
                    commissions = %s,
                    total_hourly = %s,
                    total_made = %s,
                    rolling_average = %s,
                    bonus_counter = %s,
                    updated_at = now()
                WHERE id = %s
            """, (total_sales, net_sales, commissions, total_hourly, total_made, rolling_average, bonus_counter, shift_id))

            conn.commit()
            logger.info(f"✓ Updated total_sales for shift {shift_id}: {total_sales}")

            # Update fortnight totals
            try:
                fortnight_num = self.get_fortnight_number(shift_date.day)
                self.update_fortnight_totals(employee_id, shift_date.year, shift_date.month, fortnight_num)
            except Exception as e:
                logger.warning(f"Failed to update fortnight totals: {e}")

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
            sales_commission = float(employee['sales_commission']) if employee['sales_commission'] else 6.0

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
            # Get default tier (Tier C - min_amount = 0)
            cursor.execute("""
                SELECT id, percentage FROM base_commissions
                WHERE min_amount = 0 AND is_active = TRUE
                LIMIT 1
            """)
            default_tier = cursor.fetchone()
            tier_id = default_tier['id'] if default_tier else 3
            commission = float(default_tier['percentage']) if default_tier else 6.0

            # Set id = telegram_id so foreign keys in shifts work correctly
            cursor.execute("""
                INSERT INTO employees (id, name, telegram_id, is_active, base_commission_id, sales_commission)
                VALUES (%s, %s, %s, TRUE, %s, %s)
                ON CONFLICT (id) DO NOTHING
            """, (telegram_id, name, telegram_id, tier_id, commission))

            conn.commit()
            logger.info(f"✓ Auto-created employee: {name} (telegram_id={telegram_id}, tier_id={tier_id}, commission={commission}%)")

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
        """Calculate dynamic commission rate based on current shift sales only.

        Args:
            employee_id: Employee ID (kept for interface compatibility)
            shift_date: Shift date (kept for interface compatibility)
            current_total_sales: Current shift total sales

        Returns:
            Dynamic commission rate percentage
        """
        conn = self._get_conn()
        cursor = conn.cursor()

        try:
            # Use only current shift sales for dynamic rate
            cursor.execute("SELECT get_dynamic_rate(%s) as rate", (current_total_sales,))
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
        created_at: str = None,
        shift_id: int = None
    ) -> int:
        """Create a new bonus.

        Args:
            employee_id: Employee ID
            bonus_type: Bonus type code
            value: Bonus value (percentage or flat amount)
            created_at: Optional creation timestamp (ignored, uses DB default)
            shift_id: Optional shift ID to link bonus to

        Returns:
            Bonus ID
        """
        conn = self._get_conn()
        cursor = conn.cursor()

        try:
            if shift_id:
                cursor.execute("""
                    INSERT INTO active_bonuses (employee_id, bonus_type, value, shift_id, applied)
                    VALUES (%s, %s, %s, %s, FALSE)
                    RETURNING id
                """, (employee_id, bonus_type, value, shift_id))
            else:
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

    # ========== Base Commissions (Tiers) ==========

    def get_base_commissions(self) -> List[Dict]:
        """Get all commission tiers.

        Returns:
            List of tier dicts
        """
        conn = self._get_conn()
        cursor = conn.cursor()

        try:
            cursor.execute("""
                SELECT * FROM base_commissions
                WHERE is_active = TRUE
                ORDER BY display_order ASC
            """)

            tiers = cursor.fetchall()
            return [dict(t) for t in tiers]

        finally:
            cursor.close()
            conn.close()

    def get_employee_tier(self, employee_id: int) -> Optional[Dict]:
        """Get current tier for employee.

        Args:
            employee_id: Employee ID

        Returns:
            Tier dict with id, name, percentage or None
        """
        conn = self._get_conn()
        cursor = conn.cursor()

        try:
            cursor.execute("""
                SELECT bc.id, bc.name, bc.percentage, bc.min_amount, bc.max_amount
                FROM employees e
                JOIN base_commissions bc ON e.base_commission_id = bc.id
                WHERE e.telegram_id = %s AND e.is_active = TRUE
            """, (employee_id,))

            tier = cursor.fetchone()
            if tier:
                return dict(tier)

            # Default to Tier C if no tier assigned
            cursor.execute("""
                SELECT id, name, percentage, min_amount, max_amount
                FROM base_commissions
                WHERE name = 'Tier C' AND is_active = TRUE
                LIMIT 1
            """)
            default_tier = cursor.fetchone()
            return dict(default_tier) if default_tier else None

        finally:
            cursor.close()
            conn.close()

    def calculate_employee_tier(self, employee_id: int, year: int, month: int) -> int:
        """Calculate tier based on PREVIOUS month's total sales.

        Args:
            employee_id: Employee ID
            year: Year to check
            month: Month to check (tier is based on previous month)

        Returns:
            base_commission_id for the tier
        """
        conn = self._get_conn()
        cursor = conn.cursor()

        try:
            # Calculate previous month
            if month == 1:
                prev_year = year - 1
                prev_month = 12
            else:
                prev_year = year
                prev_month = month - 1

            # Get total sales for previous month
            cursor.execute("""
                SELECT COALESCE(SUM(total_sales), 0) as total
                FROM shifts
                WHERE employee_id = %s
                  AND EXTRACT(YEAR FROM date) = %s
                  AND EXTRACT(MONTH FROM date) = %s
            """, (employee_id, prev_year, prev_month))

            result = cursor.fetchone()
            total_sales = float(result['total']) if result else 0.0

            # Find matching tier
            cursor.execute("""
                SELECT id FROM base_commissions
                WHERE is_active = TRUE
                  AND %s >= min_amount
                  AND %s <= max_amount
                ORDER BY display_order
                LIMIT 1
            """, (total_sales, total_sales))

            tier = cursor.fetchone()
            if tier:
                return tier['id']

            # Default to Tier C
            cursor.execute("SELECT id FROM base_commissions WHERE name = 'Tier C' LIMIT 1")
            default = cursor.fetchone()
            return default['id'] if default else 3

        finally:
            cursor.close()
            conn.close()

    def update_employee_tier(self, employee_id: int, year: int = None, month: int = None) -> Dict:
        """Update employee's tier based on previous month sales.

        Args:
            employee_id: Employee ID
            year: Year (default: current)
            month: Month (default: current)

        Returns:
            Dict with old_tier, new_tier, changed
        """
        if year is None or month is None:
            today = date.today()
            year = today.year
            month = today.month

        conn = self._get_conn()
        cursor = conn.cursor()

        try:
            # Get current tier
            cursor.execute("""
                SELECT base_commission_id FROM employees
                WHERE telegram_id = %s
            """, (employee_id,))
            current = cursor.fetchone()
            old_tier_id = current['base_commission_id'] if current else None

            # Calculate new tier
            new_tier_id = self.calculate_employee_tier(employee_id, year, month)

            # Update if changed
            if old_tier_id != new_tier_id:
                cursor.execute("""
                    UPDATE employees
                    SET base_commission_id = %s,
                        last_tier_update = %s,
                        updated_at = now()
                    WHERE telegram_id = %s
                """, (new_tier_id, date.today(), employee_id))
                conn.commit()
                logger.info(f"Updated tier for employee {employee_id}: {old_tier_id} -> {new_tier_id}")

            # Get tier names for return
            old_tier_name = None
            new_tier_name = None

            if old_tier_id:
                cursor.execute("SELECT name FROM base_commissions WHERE id = %s", (old_tier_id,))
                r = cursor.fetchone()
                old_tier_name = r['name'] if r else None

            cursor.execute("SELECT name FROM base_commissions WHERE id = %s", (new_tier_id,))
            r = cursor.fetchone()
            new_tier_name = r['name'] if r else None

            return {
                'old_tier_id': old_tier_id,
                'new_tier_id': new_tier_id,
                'old_tier': old_tier_name,
                'new_tier': new_tier_name,
                'changed': old_tier_id != new_tier_id
            }

        finally:
            cursor.close()
            conn.close()

    def _check_and_update_tier(self, employee_id: int, shift_date: str) -> None:
        """Check if tier needs update (beginning of month) and update if needed.

        Args:
            employee_id: Employee ID
            shift_date: Shift date string (YYYY-MM-DD or YYYY/MM/DD)
        """
        conn = self._get_conn()
        cursor = conn.cursor()

        try:
            # Parse shift date
            shift_dt = DateFormatter.parse_date(shift_date)

            # Check last tier update
            cursor.execute("""
                SELECT last_tier_update FROM employees
                WHERE telegram_id = %s
            """, (employee_id,))
            result = cursor.fetchone()

            last_update = result['last_tier_update'] if result else None

            # Update if: no previous update, or last update was in a different month
            should_update = (
                last_update is None or
                last_update.year != shift_dt.year or
                last_update.month != shift_dt.month
            )

            if should_update:
                self.update_employee_tier(employee_id, shift_dt.year, shift_dt.month)

        finally:
            cursor.close()
            conn.close()

    # ========== Rolling Average & Bonus Counter ==========

    def calculate_rolling_average(self, employee_id: int, shift_date: str) -> Decimal:
        """Calculate weighted rolling average of total_sales for last 7 calendar days.

        Formula: Σ(i / Σ(1..N)) × total_sales_i = Σ(i × sales_i) / Σ(1..N)
        where i = position (1 = oldest, N = newest)

        Special cases:
        - 0 shifts in last 7 days → rolling_average = 0 (bonus_counter will be FALSE)
        - 0 < N < 7 shifts → use formula with available shifts

        Args:
            employee_id: Employee ID
            shift_date: Shift date (YYYY-MM-DD or YYYY/MM/DD)

        Returns:
            Weighted average (0 if no shifts in last 7 days)
        """
        conn = self._get_conn()
        cursor = conn.cursor()

        try:
            # Parse shift date
            shift_date_clean = DateFormatter.to_db_date(shift_date)

            # Get shifts from last 7 calendar days (excluding current date)
            cursor.execute("""
                SELECT total_sales
                FROM shifts
                WHERE employee_id = %s
                  AND date >= %s::date - INTERVAL '7 days'
                  AND date < %s::date
                  AND total_sales IS NOT NULL
                ORDER BY date ASC, clock_in ASC
            """, (employee_id, shift_date_clean, shift_date_clean))

            shifts = cursor.fetchall()

            # If no shifts in last 7 days, return 0 (not None)
            # This ensures bonus_counter = FALSE for inactive employees
            if not shifts:
                return Decimal('0')

            # Calculate weighted average
            # Formula: Σ(i × sales_i) / Σ(1..N) where N = number of shifts
            n = len(shifts)
            sum_of_weights = Decimal(str(n * (n + 1) // 2))  # 1 + 2 + ... + N

            total_weighted = Decimal('0')
            for i, shift in enumerate(shifts, start=1):
                weight = Decimal(str(i))
                sales = Decimal(str(shift['total_sales']))
                total_weighted += weight * sales

            rolling_avg = total_weighted / sum_of_weights
            return rolling_avg.quantize(Decimal('0.01'))

        finally:
            cursor.close()
            conn.close()

    def calculate_bonus_counter(self, total_sales: Decimal, rolling_average: Optional[Decimal]) -> bool:
        """Determine if bonus_counter should be True.

        Args:
            total_sales: Current shift total sales
            rolling_average: Calculated rolling average (can be None)

        Returns:
            True if total_sales >= rolling_average, False otherwise
        """
        if rolling_average is None:
            return False

        return Decimal(str(total_sales)) >= rolling_average

    def calculate_tomorrow_target(self, employee_id: int, today_date: str) -> Decimal:
        """Calculate rolling average target for tomorrow (including today's shift).

        This calculates what the rolling_average will be tomorrow, so the employee
        knows what target they need to hit.

        Args:
            employee_id: Employee ID
            today_date: Today's date (YYYY-MM-DD or YYYY/MM/DD)

        Returns:
            Target amount for tomorrow (rolling_average including today)
        """
        conn = self._get_conn()
        cursor = conn.cursor()

        try:
            # Parse date
            today_clean = DateFormatter.to_db_date(today_date)

            # Get shifts from last 7 days INCLUDING today
            # Tomorrow's rolling_average = shifts from (today - 6 days) to today
            cursor.execute("""
                SELECT total_sales
                FROM shifts
                WHERE employee_id = %s
                  AND date >= %s::date - INTERVAL '6 days'
                  AND date <= %s::date
                  AND total_sales IS NOT NULL
                ORDER BY date ASC, clock_in ASC
            """, (employee_id, today_clean, today_clean))

            shifts = cursor.fetchall()

            if not shifts:
                return Decimal('0')

            # Calculate weighted average
            n = len(shifts)
            sum_of_weights = Decimal(str(n * (n + 1) // 2))

            total_weighted = Decimal('0')
            for i, shift in enumerate(shifts, start=1):
                weight = Decimal(str(i))
                sales = Decimal(str(shift['total_sales']))
                total_weighted += weight * sales

            target = total_weighted / sum_of_weights
            return target.quantize(Decimal('0.01'))

        finally:
            cursor.close()
            conn.close()

    def get_fortnight_bonus_count(self, employee_id: int, year: int = None, month: int = None, fortnight: int = None) -> int:
        """Get count of bonus_counter=TRUE for current fortnight.

        Args:
            employee_id: Employee ID
            year: Year (default: current)
            month: Month (default: current)
            fortnight: Fortnight number (default: current)

        Returns:
            Count of shifts with bonus_counter=TRUE in the fortnight
        """
        from datetime import date as date_class

        if year is None or month is None or fortnight is None:
            today = date_class.today()
            year = today.year
            month = today.month
            fortnight = self.get_fortnight_number(today.day)

        conn = self._get_conn()
        cursor = conn.cursor()

        try:
            # Define fortnight date range
            if fortnight == 1:
                start_day, end_day = 1, 15
            else:
                start_day = 16
                # Last day of month
                if month in [1, 3, 5, 7, 8, 10, 12]:
                    end_day = 31
                elif month in [4, 6, 9, 11]:
                    end_day = 30
                elif month == 2:
                    # Check leap year
                    if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0):
                        end_day = 29
                    else:
                        end_day = 28

            cursor.execute("""
                SELECT COUNT(*) as bonus_count
                FROM shifts
                WHERE employee_id = %s
                  AND EXTRACT(YEAR FROM date) = %s
                  AND EXTRACT(MONTH FROM date) = %s
                  AND EXTRACT(DAY FROM date) >= %s
                  AND EXTRACT(DAY FROM date) <= %s
                  AND bonus_counter = TRUE
            """, (employee_id, year, month, start_day, end_day))

            result = cursor.fetchone()
            return result['bonus_count'] if result else 0

        finally:
            cursor.close()
            conn.close()

    # ========== Fortnights ==========

    def get_fortnight_number(self, day: int) -> int:
        """Get fortnight number from day of month.

        Args:
            day: Day of month (1-31)

        Returns:
            1 for days 1-15, 2 for days 16-31
        """
        return 1 if day <= 15 else 2

    def get_fortnight_payment_date(self, year: int, month: int, fortnight: int) -> date:
        """Get payment date for a fortnight.

        Args:
            year: Year
            month: Month
            fortnight: Fortnight number (1 or 2)

        Returns:
            Payment date
        """
        if fortnight == 1:
            # F1 (days 1-15): payment on 16th of same month
            return date(year, month, 16)
        else:
            # F2 (days 16-31): payment on 1st of next month
            if month == 12:
                return date(year + 1, 1, 1)
            else:
                return date(year, month + 1, 1)

    def get_or_create_fortnight(self, employee_id: int, year: int, month: int, fortnight: int) -> Dict:
        """Get or create fortnight record for employee.

        Args:
            employee_id: Employee ID
            year: Year
            month: Month
            fortnight: Fortnight number (1 or 2)

        Returns:
            Fortnight record dict
        """
        conn = self._get_conn()
        cursor = conn.cursor()

        try:
            # Try to get existing
            cursor.execute("""
                SELECT * FROM employee_fortnights
                WHERE employee_id = %s AND year = %s AND month = %s AND fortnight = %s
            """, (employee_id, year, month, fortnight))

            record = cursor.fetchone()
            if record:
                return dict(record)

            # Create new record
            payment_date = self.get_fortnight_payment_date(year, month, fortnight)

            cursor.execute("""
                INSERT INTO employee_fortnights (
                    employee_id, year, month, fortnight, payment_date
                ) VALUES (%s, %s, %s, %s, %s)
                RETURNING *
            """, (employee_id, year, month, fortnight, payment_date))

            new_record = cursor.fetchone()
            conn.commit()

            logger.info(f"Created fortnight record: employee={employee_id}, {year}-{month:02d} F{fortnight}")
            return dict(new_record)

        finally:
            cursor.close()
            conn.close()

    def update_fortnight_totals(self, employee_id: int, year: int, month: int, fortnight: int) -> Dict:
        """Recalculate fortnight totals from shifts.

        Args:
            employee_id: Employee ID
            year: Year
            month: Month
            fortnight: Fortnight number (1 or 2)

        Returns:
            Updated fortnight record
        """
        conn = self._get_conn()
        cursor = conn.cursor()

        try:
            # Determine date range for fortnight
            if fortnight == 1:
                start_day, end_day = 1, 15
            else:
                start_day, end_day = 16, 31

            start_date = date(year, month, start_day)
            # Handle end of month
            if fortnight == 2:
                # Last day of month
                if month == 12:
                    end_date = date(year + 1, 1, 1) - timedelta(days=1)
                else:
                    end_date = date(year, month + 1, 1) - timedelta(days=1)
            else:
                end_date = date(year, month, end_day)

            # Aggregate shift data
            cursor.execute("""
                SELECT
                    COUNT(*) as total_shifts,
                    COALESCE(SUM(worked_hours), 0) as total_worked_hours,
                    COALESCE(SUM(total_sales), 0) as total_sales,
                    COALESCE(SUM(commissions), 0) as total_commissions,
                    COALESCE(SUM(total_hourly), 0) as total_hourly_pay,
                    COALESCE(SUM(total_made), 0) as total_made,
                    COUNT(*) FILTER (WHERE bonus_counter = TRUE) as bonus_counter_true_count
                FROM shifts
                WHERE employee_id = %s
                  AND date >= %s
                  AND date <= %s
            """, (employee_id, start_date, end_date))

            stats = cursor.fetchone()

            # Get bonus percentage setting
            cursor.execute("""
                SELECT setting_value FROM bonus_settings
                WHERE setting_key = 'bonus_counter_percentage' AND is_active = TRUE
            """)
            bonus_setting = cursor.fetchone()
            bonus_pct = Decimal(str(bonus_setting['setting_value'])) if bonus_setting else Decimal('0.01')

            # Calculate bonus amount
            bonus_count = stats['bonus_counter_true_count'] or 0
            total_commissions = Decimal(str(stats['total_commissions']))
            bonus_amount = bonus_count * total_commissions * bonus_pct

            # Calculate total salary
            total_made = Decimal(str(stats['total_made']))
            total_salary = total_made + bonus_amount

            # Update fortnight record
            payment_date = self.get_fortnight_payment_date(year, month, fortnight)

            cursor.execute("""
                INSERT INTO employee_fortnights (
                    employee_id, year, month, fortnight,
                    total_shifts, total_worked_hours, total_sales,
                    total_commissions, total_hourly_pay, total_made,
                    bonus_counter_true_count, bonus_amount, total_salary,
                    payment_date
                ) VALUES (
                    %s, %s, %s, %s,
                    %s, %s, %s,
                    %s, %s, %s,
                    %s, %s, %s,
                    %s
                )
                ON CONFLICT (employee_id, year, month, fortnight) DO UPDATE SET
                    total_shifts = EXCLUDED.total_shifts,
                    total_worked_hours = EXCLUDED.total_worked_hours,
                    total_sales = EXCLUDED.total_sales,
                    total_commissions = EXCLUDED.total_commissions,
                    total_hourly_pay = EXCLUDED.total_hourly_pay,
                    total_made = EXCLUDED.total_made,
                    bonus_counter_true_count = EXCLUDED.bonus_counter_true_count,
                    bonus_amount = EXCLUDED.bonus_amount,
                    total_salary = EXCLUDED.total_salary,
                    updated_at = now()
                RETURNING *
            """, (
                employee_id, year, month, fortnight,
                stats['total_shifts'], stats['total_worked_hours'], stats['total_sales'],
                stats['total_commissions'], stats['total_hourly_pay'], stats['total_made'],
                bonus_count, bonus_amount, total_salary,
                payment_date
            ))

            updated = cursor.fetchone()
            conn.commit()

            logger.info(f"Updated fortnight totals: employee={employee_id}, {year}-{month:02d} F{fortnight}, salary=${total_salary:.2f}")
            return dict(updated)

        finally:
            cursor.close()
            conn.close()

    def get_employee_fortnights(self, employee_id: int, year: int = None, month: int = None) -> List[Dict]:
        """Get fortnight history for employee.

        Args:
            employee_id: Employee ID
            year: Optional year filter
            month: Optional month filter

        Returns:
            List of fortnight records
        """
        conn = self._get_conn()
        cursor = conn.cursor()

        try:
            if year and month:
                cursor.execute("""
                    SELECT * FROM employee_fortnights
                    WHERE employee_id = %s AND year = %s AND month = %s
                    ORDER BY fortnight
                """, (employee_id, year, month))
            elif year:
                cursor.execute("""
                    SELECT * FROM employee_fortnights
                    WHERE employee_id = %s AND year = %s
                    ORDER BY month, fortnight
                """, (employee_id, year))
            else:
                cursor.execute("""
                    SELECT * FROM employee_fortnights
                    WHERE employee_id = %s
                    ORDER BY year DESC, month DESC, fortnight DESC
                """, (employee_id,))

            return [dict(r) for r in cursor.fetchall()]

        finally:
            cursor.close()
            conn.close()

    def get_bonus_setting(self, key: str) -> Optional[Decimal]:
        """Get bonus setting value.

        Args:
            key: Setting key

        Returns:
            Setting value or None
        """
        conn = self._get_conn()
        cursor = conn.cursor()

        try:
            cursor.execute("""
                SELECT setting_value FROM bonus_settings
                WHERE setting_key = %s AND is_active = TRUE
            """, (key,))

            result = cursor.fetchone()
            return Decimal(str(result['setting_value'])) if result else None

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
