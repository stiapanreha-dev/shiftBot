"""PostgreSQL service adapted to existing database schema.

This service works with the EXISTING normalized PostgreSQL schema that has:
- employees table (not employee_settings)
- products table (separate)
- shift_products table (normalized many-to-many)
- shifts table (without product columns)

It provides the same interface as SheetsService for backward compatibility.

Author: Claude Code (PROMPT 4.1 - PostgreSQL Migration - Adapted)
Date: 2025-11-11
Version: 3.0.1
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


class PostgresServiceAdapted:
    """PostgreSQL service adapted to existing schema.

    Drop-in replacement for SheetsService that works with normalized PostgreSQL schema.
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
            logger.info("PostgreSQL connection initialized successfully")
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
            cursor.execute("SELECT nextval('shifts_id_seq')")
            next_id = cursor.fetchone()['nextval']
            return next_id
        finally:
            cursor.close()
            conn.close()

    def create_shift(self, shift_data: Dict) -> int:
        """Create a new shift with products.

        Args:
            shift_data: Dict containing shift information including product sales

        Returns:
            shift_id of created shift
        """
        conn = self._get_conn()
        cursor = conn.cursor()

        try:
            # Extract shift data
            employee_id = shift_data['employee_id']
            employee_name = shift_data['employee_name']
            shift_date = shift_data['shift_date']
            time_in = shift_data['time_in']
            time_out = shift_data.get('time_out')

            # Parse datetime
            clock_in = f"{shift_date} {time_in}"
            clock_out = f"{shift_date} {time_out}" if time_out else None

            # Calculate hours if clock_out provided
            worked_hours = shift_data.get('total_hours', 0)

            # Sales and commission
            total_sales = Decimal(str(shift_data.get('total_sales', 0)))
            net_sales = total_sales  # Assuming net_sales = total_sales
            commission_pct = Decimal(str(shift_data.get('total_commission_pct', 0)))
            commissions = total_sales * commission_pct / 100
            total_per_hour = commissions / Decimal(str(worked_hours)) if worked_hours and worked_hours > 0 else Decimal('0')
            total_made = commissions

            # Insert shift
            cursor.execute("""
                INSERT INTO shifts (
                    date, employee_id, employee_name, clock_in, clock_out, worked_hours,
                    total_sales, net_sales, commission_pct, total_per_hour, commissions, total_made
                ) VALUES (
                    %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s
                )
                RETURNING id
            """, (
                shift_date, employee_id, employee_name, clock_in, clock_out, worked_hours,
                total_sales, net_sales, commission_pct, total_per_hour, commissions, total_made
            ))

            shift_id = cursor.fetchone()['id']

            # Insert products
            for product_name in Config.PRODUCTS:
                sales_key = f"{product_name.lower()}_sales"
                amount = Decimal(str(shift_data.get(sales_key, 0)))

                if amount > 0:
                    # Get product_id
                    cursor.execute("SELECT id FROM products WHERE name = %s", (product_name,))
                    product = cursor.fetchone()

                    if product:
                        cursor.execute("""
                            INSERT INTO shift_products (shift_id, product_id, amount)
                            VALUES (%s, %s, %s)
                        """, (shift_id, product['id'], amount))

            conn.commit()
            logger.info(f"Created shift {shift_id} for employee {employee_id}")
            return shift_id

        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to create shift: {e}")
            raise
        finally:
            cursor.close()
            conn.close()

    def get_shift_by_id(self, shift_id: int) -> Optional[Dict]:
        """Get shift data by ID with product sales.

        Args:
            shift_id: Shift ID

        Returns:
            Shift data dict or None if not found
        """
        conn = self._get_conn()
        cursor = conn.cursor()

        try:
            # Get shift base data
            cursor.execute("""
                SELECT * FROM shifts WHERE id = %s
            """, (shift_id,))

            shift = cursor.fetchone()
            if not shift:
                return None

            result = dict(shift)

            # Rename fields for compatibility with SheetsService interface
            result['shift_id'] = result.pop('id')
            result['shift_date'] = str(result.pop('date'))
            result['time_in'] = result['clock_in'].strftime('%H:%M') if result.get('clock_in') else ''
            result['time_out'] = result['clock_out'].strftime('%H:%M') if result.get('clock_out') else ''
            result['total_commission_pct'] = result.pop('commission_pct')
            result['commission_amount'] = result.pop('commissions')

            # Get product sales
            cursor.execute("""
                SELECT p.name, sp.amount
                FROM shift_products sp
                JOIN products p ON sp.product_id = p.id
                WHERE sp.shift_id = %s
            """, (shift_id,))

            products = cursor.fetchall()

            # Add product sales to result
            for product in Config.PRODUCTS:
                sales_key = f"{product.lower()}_sales"
                result[sales_key] = Decimal('0')

            for product_row in products:
                product_name = product_row['name']
                sales_key = f"{product_name.lower()}_sales"
                result[sales_key] = product_row['amount']

            return result

        finally:
            cursor.close()
            conn.close()

    def update_shift_field(self, shift_id: int, field: str, value: str) -> bool:
        """Update a single field of a shift.

        Args:
            shift_id: Shift ID
            field: Field name to update
            value: New value

        Returns:
            True if successful
        """
        conn = self._get_conn()
        cursor = conn.cursor()

        # Map field names from Sheets to PostgreSQL columns
        field_mapping = {
            'Clock in': 'clock_in',
            'Clock out': 'clock_out',
            'Worked hours/shift': 'worked_hours',
            'Total sales': 'total_sales',
        }

        pg_field = field_mapping.get(field, field)

        try:
            # Special handling for time fields
            if pg_field in ['clock_in', 'clock_out']:
                # Get current date
                cursor.execute("SELECT date FROM shifts WHERE id = %s", (shift_id,))
                shift = cursor.fetchone()
                if not shift:
                    return False

                shift_date = shift['date']
                full_datetime = f"{shift_date} {value}"

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
            logger.info(f"Updated shift {shift_id}: {pg_field} = {value}")
            return True

        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to update shift field: {e}")
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
            cursor.execute("SELECT commission_pct FROM shifts WHERE id = %s", (shift_id,))
            shift = cursor.fetchone()

            if not shift:
                return False

            commission_pct = shift['commission_pct']
            commissions = total_sales * commission_pct / 100

            # Update shift
            cursor.execute("""
                UPDATE shifts
                SET total_sales = %s,
                    net_sales = %s,
                    commissions = %s,
                    total_made = %s,
                    updated_at = now()
                WHERE id = %s
            """, (total_sales, total_sales, commissions, commissions, shift_id))

            conn.commit()
            logger.info(f"Updated total_sales for shift {shift_id}: {total_sales}")
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
            List of shift dicts
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

            # Convert to format compatible with SheetsService
            result = []
            for shift in shifts:
                shift_dict = dict(shift)
                shift_dict['shift_id'] = shift_dict.pop('id')
                shift_dict['shift_date'] = str(shift_dict.pop('date'))
                result.append(shift_dict)

            return result

        finally:
            cursor.close()
            conn.close()

    def get_all_shifts(self) -> List[Dict]:
        """Get all shifts.

        Returns:
            List of all shift dicts
        """
        conn = self._get_conn()
        cursor = conn.cursor()

        try:
            cursor.execute("""
                SELECT * FROM shifts
                ORDER BY date DESC, clock_in DESC
            """)

            shifts = cursor.fetchall()
            return [dict(row) for row in shifts]

        finally:
            cursor.close()
            conn.close()

    # ========== Employee Management ==========

    def get_employee_settings(self, employee_id: int) -> Optional[Dict]:
        """Get employee settings.

        Note: Returns compatible format with SheetsService (base_commission_pct, etc.)

        Args:
            employee_id: Employee ID

        Returns:
            Employee settings dict or None
        """
        conn = self._get_conn()
        cursor = conn.cursor()

        try:
            cursor.execute("""
                SELECT * FROM employees WHERE id = %s AND is_active = TRUE
            """, (employee_id,))

            employee = cursor.fetchone()

            if not employee:
                return None

            # For compatibility: assume base_commission_pct from dynamic_rates or default
            # This needs to be properly implemented based on your business logic
            result = dict(employee)
            result['employee_id'] = result.pop('id')
            result['employee_name'] = result.pop('name')
            result['base_commission_pct'] = Decimal('8.0')  # Default, should be fetched from somewhere
            result['active'] = result.pop('is_active')

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
            logger.info(f"Created default settings for employee {employee_id}")
        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to create default employee settings: {e}")
            raise
        finally:
            cursor.close()
            conn.close()

    # ========== Dynamic Rates ==========

    def get_dynamic_rates(self) -> List[Dict]:
        """Get all dynamic commission rates.

        Returns:
            List of rate dicts
        """
        conn = self._get_conn()
        cursor = conn.cursor()

        try:
            cursor.execute("""
                SELECT * FROM dynamic_rates
                ORDER BY min_sales ASC
            """)

            return [dict(row) for row in cursor.fetchall()]
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
            # Use the database function get_dynamic_rate
            cursor.execute("SELECT get_dynamic_rate(%s) as rate", (current_total_sales,))
            result = cursor.fetchone()
            return float(result['rate']) if result else 0.0

        finally:
            cursor.close()
            conn.close()

    # ========== Ranks ==========

    def get_ranks(self) -> List[Dict]:
        """Get all ranks.

        Returns:
            List of rank dicts
        """
        conn = self._get_conn()
        cursor = conn.cursor()

        try:
            cursor.execute("""
                SELECT * FROM ranks
                ORDER BY bonus_pct DESC
            """)

            return [dict(row) for row in cursor.fetchall()]
        finally:
            cursor.close()
            conn.close()

    def get_employee_rank(self, employee_id: int, year: int, month: int) -> Optional[Dict]:
        """Get employee rank for a specific month using database function.

        Args:
            employee_id: Employee ID
            year: Year
            month: Month (1-12)

        Returns:
            Dict with rank info or None
        """
        conn = self._get_conn()
        cursor = conn.cursor()

        try:
            # Use database function
            cursor.execute(
                "SELECT get_employee_rank(%s, %s, %s) as rank_name",
                (employee_id, year, month)
            )

            result = cursor.fetchone()
            if not result or not result['rank_name']:
                return None

            rank_name = result['rank_name']

            # Get rank details
            cursor.execute("SELECT * FROM ranks WHERE name = %s", (rank_name,))
            rank = cursor.fetchone()

            return dict(rank) if rank else None

        finally:
            cursor.close()
            conn.close()

    def update_employee_rank(
        self,
        employee_id: int,
        year: int,
        month: int,
        rank_name: str
    ) -> None:
        """Update employee rank for a month.

        Args:
            employee_id: Employee ID
            year: Year
            month: Month (1-12)
            rank_name: Rank name
        """
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
            month_val = f"{year}-{month:02d}"

            # Upsert employee rank
            cursor.execute("""
                INSERT INTO employee_ranks (employee_id, month, rank_id)
                VALUES (%s, %s, %s)
                ON CONFLICT (employee_id, month) DO UPDATE
                SET rank_id = EXCLUDED.rank_id
            """, (employee_id, month_val, rank_id))

            conn.commit()
            logger.info(f"Updated rank for employee {employee_id} ({year}-{month:02d}): {rank_name}")

        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to update employee rank: {e}")
            raise
        finally:
            cursor.close()
            conn.close()

    # ========== Active Bonuses ==========

    def get_shift_applied_bonuses(self, shift_id: int) -> List[Dict]:
        """Get bonuses applied to a shift.

        Args:
            shift_id: Shift ID

        Returns:
            List of bonus dicts
        """
        conn = self._get_conn()
        cursor = conn.cursor()

        try:
            cursor.execute("""
                SELECT * FROM active_bonuses
                WHERE shift_id = %s
            """, (shift_id,))

            return [dict(row) for row in cursor.fetchall()]
        finally:
            cursor.close()
            conn.close()

    def apply_bonus(self, shift_id: int, bonus_type: str, bonus_pct: Decimal, reason: str = "") -> None:
        """Apply a bonus to a shift.

        Args:
            shift_id: Shift ID
            bonus_type: Bonus type
            bonus_pct: Bonus percentage
            reason: Reason for bonus
        """
        conn = self._get_conn()
        cursor = conn.cursor()

        try:
            # Get employee_id from shift
            cursor.execute("SELECT employee_id FROM shifts WHERE id = %s", (shift_id,))
            shift = cursor.fetchone()

            if not shift:
                logger.error(f"Shift {shift_id} not found")
                return

            employee_id = shift['employee_id']

            cursor.execute("""
                INSERT INTO active_bonuses (employee_id, shift_id, bonus_type, bonus_pct, notes)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (shift_id, bonus_type) DO UPDATE
                SET bonus_pct = EXCLUDED.bonus_pct, notes = EXCLUDED.notes
            """, (employee_id, shift_id, bonus_type, bonus_pct, reason))

            conn.commit()
            logger.info(f"Applied bonus to shift {shift_id}: {bonus_type} ({bonus_pct}%)")

        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to apply bonus: {e}")
            raise
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
        for product in Config.PRODUCTS:
            sales_key = f"{product.lower()}_sales"
            if shift.get(sales_key, 0) > 0:
                models.append(product)

        return models


# For backward compatibility
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    service = PostgresServiceAdapted()
    print("PostgresServiceAdapted initialized successfully")

    # Test connection
    try:
        shifts = service.get_all_shifts()
        print(f"Total shifts in database: {len(shifts)}")
        if shifts:
            print(f"Latest shift: ID={shifts[0]['id']}, Employee={shifts[0]['employee_name']}")
    except Exception as e:
        print(f"Error: {e}")
