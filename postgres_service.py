"""PostgreSQL service for shift data management.

This is a drop-in replacement for SheetsService that uses PostgreSQL
instead of Google Sheets for all operations.

Author: Claude Code (PROMPT 4.1 - PostgreSQL Migration)
Date: 2025-11-11
Version: 3.0.0
"""

import logging
from typing import Dict, List, Optional
from decimal import Decimal
from datetime import datetime, date
import psycopg2
from psycopg2 import sql, extras

from pg_schema import get_db_connection
from config import Config
from time_utils import parse_dt

logger = logging.getLogger(__name__)


class PostgresService:
    """Service for managing shift data in PostgreSQL.

    This class provides the same interface as SheetsService but uses
    PostgreSQL as the backend instead of Google Sheets.
    """

    def __init__(self, cache_manager=None, **db_params):
        """Initialize PostgreSQL service.

        Args:
            cache_manager: Optional CacheManager instance (for compatibility)
            **db_params: PostgreSQL connection parameters
        """
        self.db_params = db_params or {}
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
            cursor.execute("SELECT COALESCE(MAX(shift_id), 0) + 1 FROM shifts")
            next_id = cursor.fetchone()['coalesce']
            return next_id
        finally:
            cursor.close()
            conn.close()

    def create_shift(self, shift_data: Dict) -> int:
        """Create a new shift.

        Args:
            shift_data: Dict containing shift information

        Returns:
            shift_id of created shift
        """
        conn = self._get_conn()
        cursor = conn.cursor()

        try:
            # Extract data
            employee_id = shift_data['employee_id']
            employee_name = shift_data['employee_name']
            shift_date = shift_data['shift_date']
            time_in = shift_data['time_in']
            time_out = shift_data.get('time_out')
            total_hours = shift_data.get('total_hours')

            # Product sales
            bella_sales = Decimal(str(shift_data.get('bella_sales', 0)))
            laura_sales = Decimal(str(shift_data.get('laura_sales', 0)))
            sophie_sales = Decimal(str(shift_data.get('sophie_sales', 0)))
            alice_sales = Decimal(str(shift_data.get('alice_sales', 0)))
            emma_sales = Decimal(str(shift_data.get('emma_sales', 0)))
            molly_sales = Decimal(str(shift_data.get('molly_sales', 0)))
            total_sales = Decimal(str(shift_data.get('total_sales', 0)))

            # Commission
            base_commission_pct = Decimal(str(shift_data.get('base_commission_pct', 0)))
            dynamic_commission_pct = Decimal(str(shift_data.get('dynamic_commission_pct', 0)))
            bonus_commission_pct = Decimal(str(shift_data.get('bonus_commission_pct', 0)))
            total_commission_pct = Decimal(str(shift_data.get('total_commission_pct', 0)))
            commission_amount = Decimal(str(shift_data.get('commission_amount', 0)))

            cursor.execute("""
                INSERT INTO shifts (
                    employee_id, employee_name, shift_date, time_in, time_out, total_hours,
                    bella_sales, laura_sales, sophie_sales, alice_sales, emma_sales, molly_sales, total_sales,
                    base_commission_pct, dynamic_commission_pct, bonus_commission_pct,
                    total_commission_pct, commission_amount, status
                ) VALUES (
                    %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s
                )
                RETURNING shift_id
            """, (
                employee_id, employee_name, shift_date, time_in, time_out, total_hours,
                bella_sales, laura_sales, sophie_sales, alice_sales, emma_sales, molly_sales, total_sales,
                base_commission_pct, dynamic_commission_pct, bonus_commission_pct,
                total_commission_pct, commission_amount, 'active'
            ))

            shift_id = cursor.fetchone()['shift_id']
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
        """Get shift data by ID.

        Args:
            shift_id: Shift ID

        Returns:
            Shift data dict or None if not found
        """
        conn = self._get_conn()
        cursor = conn.cursor()

        try:
            cursor.execute("""
                SELECT * FROM shifts WHERE shift_id = %s
            """, (shift_id,))

            result = cursor.fetchone()
            return dict(result) if result else None
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
            'Clock in': 'time_in',
            'Clock out': 'time_out',
            'Worked hours/shift': 'total_hours',
            'Bella': 'bella_sales',
            'Laura': 'laura_sales',
            'Sophie': 'sophie_sales',
            'Alice': 'alice_sales',
            'Emma': 'emma_sales',
            'Molly': 'molly_sales',
            'Total sales': 'total_sales',
        }

        pg_field = field_mapping.get(field, field)

        try:
            cursor.execute(
                sql.SQL("UPDATE shifts SET {} = %s, updated_at = CURRENT_TIMESTAMP WHERE shift_id = %s").format(
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
        return self.update_shift_field(shift_id, 'total_sales', str(total_sales))

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
                ORDER BY shift_date DESC, time_in DESC
                LIMIT %s
            """, (employee_id, limit))

            return [dict(row) for row in cursor.fetchall()]
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
                ORDER BY shift_date DESC, time_in DESC
            """)

            return [dict(row) for row in cursor.fetchall()]
        finally:
            cursor.close()
            conn.close()

    # ========== Employee Settings ==========

    def get_employee_settings(self, employee_id: int) -> Optional[Dict]:
        """Get employee settings.

        Args:
            employee_id: Employee ID

        Returns:
            Employee settings dict or None
        """
        conn = self._get_conn()
        cursor = conn.cursor()

        try:
            cursor.execute("""
                SELECT * FROM employee_settings WHERE employee_id = %s AND active = TRUE
            """, (employee_id,))

            result = cursor.fetchone()
            return dict(result) if result else None
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
                INSERT INTO employee_settings (employee_id, employee_name, base_commission_pct, active)
                VALUES (%s, %s, %s, TRUE)
                ON CONFLICT (employee_id) DO NOTHING
            """, (employee_id, f"Employee {employee_id}", Decimal("8.0")))

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
        """Calculate dynamic commission rate based on total sales.

        Args:
            employee_id: Employee ID
            shift_date: Shift date (YYYY-MM-DD)
            current_total_sales: Current shift total sales

        Returns:
            Dynamic commission rate percentage
        """
        # Calculate total sales for the month (including current shift)
        conn = self._get_conn()
        cursor = conn.cursor()

        try:
            # Parse date
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
                AND shift_date >= %s
                AND shift_date < %s
            """, (employee_id, month_start, month_end))

            monthly_total = cursor.fetchone()['total']
            total_with_current = monthly_total + current_total_sales

            # Get dynamic rates
            rates = self.get_dynamic_rates()

            # Find applicable rate
            for rate in rates:
                min_sales = rate['min_sales']
                max_sales = rate['max_sales']

                if max_sales is None:
                    if total_with_current >= min_sales:
                        return float(rate['rate_pct'])
                else:
                    if min_sales <= total_with_current <= max_sales:
                        return float(rate['rate_pct'])

            return 0.0

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
        """Get employee rank for a specific month.

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
            month_str = f"{year}-{month:02d}"

            cursor.execute("""
                SELECT er.*, r.rank_name, r.bonus_pct, r.description
                FROM employee_ranks er
                JOIN ranks r ON er.rank_id = r.id
                WHERE er.employee_id = %s AND er.month = %s
            """, (employee_id, month_str))

            result = cursor.fetchone()
            return dict(result) if result else None
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
            month_str = f"{year}-{month:02d}"

            # Get rank_id
            cursor.execute("SELECT id FROM ranks WHERE rank_name = %s", (rank_name,))
            rank = cursor.fetchone()

            if not rank:
                logger.error(f"Rank '{rank_name}' not found")
                return

            rank_id = rank['id']

            # Upsert employee rank
            cursor.execute("""
                INSERT INTO employee_ranks (employee_id, month, rank_id)
                VALUES (%s, %s, %s)
                ON CONFLICT (employee_id, month) DO UPDATE
                SET rank_id = EXCLUDED.rank_id
            """, (employee_id, month_str, rank_id))

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
            cursor.execute("""
                INSERT INTO active_bonuses (shift_id, bonus_type, bonus_pct, reason)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (shift_id, bonus_type) DO UPDATE
                SET bonus_pct = EXCLUDED.bonus_pct, reason = EXCLUDED.reason
            """, (shift_id, bonus_type, bonus_pct, reason))

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
        conn = self._get_conn()
        cursor = conn.cursor()

        try:
            # Build WHERE clause for models
            model_conditions = []
            for model in models:
                sales_col = f"{model.lower()}_sales"
                model_conditions.append(f"{sales_col} > 0")

            if not model_conditions:
                return None

            models_clause = " OR ".join(model_conditions)

            query = f"""
                SELECT * FROM shifts
                WHERE employee_id = %s
                AND (shift_date < %s OR (shift_date = %s AND time_in < %s))
                AND ({models_clause})
                ORDER BY shift_date DESC, time_in DESC
                LIMIT 1
            """

            cursor.execute(query, (employee_id, shift_date, shift_date, time_in))

            result = cursor.fetchone()
            return dict(result) if result else None

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
            sales_col = f"{model.lower()}_sales"
            cutoff_date = datetime.strptime(shift_date, "%Y-%m-%d").date()

            query = f"""
                SELECT * FROM shifts
                WHERE employee_id = %s
                AND shift_date >= %s - INTERVAL '%s days'
                AND (shift_date < %s OR (shift_date = %s AND time_in < %s))
                AND {sales_col} > 0
                ORDER BY shift_date DESC, time_in DESC
            """

            cursor.execute(query, (employee_id, cutoff_date, days_back, shift_date, shift_date, time_in))

            return [dict(row) for row in cursor.fetchall()]

        finally:
            cursor.close()
            conn.close()


# For backward compatibility
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    service = PostgresService()
    print("PostgresService initialized successfully")

    # Test connection
    print(f"Next shift ID: {service.get_next_id()}")
    print(f"Ranks count: {len(service.get_ranks())}")
