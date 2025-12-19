"""Shift repository for shift data access."""

import logging
from decimal import Decimal
from datetime import date, datetime
from typing import Optional, List, Dict, Any

from .base import BaseRepository
from services.formatters import DateFormatter

logger = logging.getLogger(__name__)


class ShiftRepository(BaseRepository):
    """Repository for shift CRUD operations.

    This repository handles only data access. Business logic
    (commission calculation, tier updates, etc.) should be in services.
    """

    def create(
        self,
        employee_id: int,
        employee_name: str,
        shift_date: str,
        clock_in: Optional[str],
        clock_out: Optional[str],
        worked_hours: Decimal,
        total_sales: Decimal,
        net_sales: Decimal,
        commission_pct: Decimal,
        total_hourly: Decimal,
        commissions: Decimal,
        total_made: Decimal,
        rolling_average: Optional[Decimal] = None,
        bonus_counter: bool = False,
        synced_to_sheets: bool = False
    ) -> int:
        """Create new shift.

        Args:
            employee_id: Employee telegram ID
            employee_name: Employee name
            shift_date: Shift date (YYYY-MM-DD)
            clock_in: Clock in datetime
            clock_out: Clock out datetime
            worked_hours: Hours worked
            total_sales: Total sales amount
            net_sales: Net sales (80% of total)
            commission_pct: Commission percentage
            total_hourly: Hourly pay
            commissions: Commission amount
            total_made: Total earnings
            rolling_average: 7-day rolling average
            bonus_counter: Whether bonus counter is true
            synced_to_sheets: Whether synced to Google Sheets

        Returns:
            New shift ID
        """
        query = """
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
                %s
            )
            RETURNING id
        """
        params = (
            shift_date, employee_id, employee_name,
            clock_in, clock_out, worked_hours,
            total_sales, net_sales, commission_pct,
            total_hourly, commissions, total_made,
            rolling_average, bonus_counter,
            synced_to_sheets
        )

        shift_id = self._execute_insert(query, params)
        logger.info(f"Created shift {shift_id} for employee {employee_id}")
        return shift_id

    def get_by_id(self, shift_id: int) -> Optional[Dict]:
        """Get shift by ID.

        Args:
            shift_id: Shift ID

        Returns:
            Shift data as dict or None
        """
        query = "SELECT * FROM shifts WHERE id = %s"
        return self._execute_one(query, (shift_id,))

    def get_by_id_formatted(self, shift_id: int) -> Optional[Dict]:
        """Get shift by ID in legacy SheetsService format.

        This method provides backward compatibility with existing code
        that expects the old field names.

        Args:
            shift_id: Shift ID

        Returns:
            Shift data in legacy format or None
        """
        shift = self.get_by_id(shift_id)
        if not shift:
            return None

        return self._to_legacy_format(shift)

    def get_all(self, limit: int = 1000) -> List[Dict]:
        """Get all shifts.

        Args:
            limit: Maximum number of shifts to return

        Returns:
            List of shifts
        """
        query = "SELECT * FROM shifts ORDER BY id DESC LIMIT %s"
        return self._execute_many(query, (limit,))

    def get_by_employee(
        self,
        employee_id: int,
        limit: int = 10,
        offset: int = 0
    ) -> List[Dict]:
        """Get shifts for specific employee.

        Args:
            employee_id: Employee telegram ID
            limit: Maximum number of shifts
            offset: Number of shifts to skip

        Returns:
            List of shifts
        """
        query = """
            SELECT * FROM shifts
            WHERE employee_id = %s
            ORDER BY date DESC, id DESC
            LIMIT %s OFFSET %s
        """
        return self._execute_many(query, (employee_id, limit, offset))

    def get_last_shifts(self, employee_id: int, limit: int = 3) -> List[Dict]:
        """Get last N shifts for employee in legacy format.

        Args:
            employee_id: Employee telegram ID
            limit: Number of shifts to return

        Returns:
            List of shifts in legacy format
        """
        shifts = self.get_by_employee(employee_id, limit=limit)
        return [self._to_legacy_format(s) for s in shifts]

    def update_field(self, shift_id: int, field: str, value: Any) -> bool:
        """Update single field of shift.

        Args:
            shift_id: Shift ID
            field: Field name (PostgreSQL column name)
            value: New value

        Returns:
            True if updated
        """
        # Validate field name to prevent SQL injection
        allowed_fields = {
            'clock_in', 'clock_out', 'worked_hours',
            'total_sales', 'net_sales', 'commission_pct',
            'total_hourly', 'commissions', 'total_made',
            'rolling_average', 'bonus_counter', 'synced_to_sheets'
        }

        if field not in allowed_fields:
            logger.warning(f"Attempted to update invalid field: {field}")
            return False

        query = f"UPDATE shifts SET {field} = %s, updated_at = now() WHERE id = %s"
        affected = self._execute_update(query, (value, shift_id))
        return affected > 0

    def update_financials(
        self,
        shift_id: int,
        total_sales: Decimal,
        net_sales: Decimal,
        commissions: Decimal,
        total_hourly: Decimal,
        total_made: Decimal,
        rolling_average: Optional[Decimal] = None,
        bonus_counter: bool = False
    ) -> bool:
        """Update financial fields of shift.

        Args:
            shift_id: Shift ID
            total_sales: New total sales
            net_sales: New net sales
            commissions: New commissions
            total_hourly: New hourly pay
            total_made: New total made
            rolling_average: New rolling average
            bonus_counter: New bonus counter value

        Returns:
            True if updated
        """
        query = """
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
        """
        affected = self._execute_update(query, (
            total_sales, net_sales, commissions,
            total_hourly, total_made,
            rolling_average, bonus_counter,
            shift_id
        ))
        return affected > 0

    def update_clock_times(
        self,
        shift_id: int,
        clock_in: Optional[str] = None,
        clock_out: Optional[str] = None
    ) -> bool:
        """Update clock in/out times.

        Args:
            shift_id: Shift ID
            clock_in: New clock in time
            clock_out: New clock out time

        Returns:
            True if updated
        """
        updates = []
        params = []

        if clock_in is not None:
            updates.append("clock_in = %s")
            params.append(DateFormatter.to_db_datetime(clock_in))

        if clock_out is not None:
            updates.append("clock_out = %s")
            params.append(DateFormatter.to_db_datetime(clock_out))

        if not updates:
            return False

        updates.append("updated_at = now()")
        params.append(shift_id)

        query = f"UPDATE shifts SET {', '.join(updates)} WHERE id = %s"
        affected = self._execute_update(query, tuple(params))
        return affected > 0

    def get_for_date_range(
        self,
        employee_id: int,
        start_date: str,
        end_date: str
    ) -> List[Dict]:
        """Get shifts for employee within date range.

        Args:
            employee_id: Employee telegram ID
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)

        Returns:
            List of shifts
        """
        query = """
            SELECT * FROM shifts
            WHERE employee_id = %s
              AND date >= %s::date
              AND date <= %s::date
            ORDER BY date ASC
        """
        return self._execute_many(query, (employee_id, start_date, end_date))

    def get_monthly_total_sales(
        self,
        employee_id: int,
        year: int,
        month: int
    ) -> Decimal:
        """Get total sales for employee in given month.

        Args:
            employee_id: Employee telegram ID
            year: Year
            month: Month (1-12)

        Returns:
            Total sales amount
        """
        query = """
            SELECT COALESCE(SUM(total_sales), 0) as total
            FROM shifts
            WHERE employee_id = %s
              AND EXTRACT(YEAR FROM date) = %s
              AND EXTRACT(MONTH FROM date) = %s
        """
        result = self._execute_one(query, (employee_id, year, month))
        return Decimal(str(result['total'])) if result else Decimal('0')

    def delete(self, shift_id: int) -> bool:
        """Delete shift by ID.

        Args:
            shift_id: Shift ID

        Returns:
            True if deleted
        """
        query = "DELETE FROM shifts WHERE id = %s"
        affected = self._execute_update(query, (shift_id,))
        return affected > 0

    def _to_legacy_format(self, shift: Dict) -> Dict:
        """Convert shift to legacy SheetsService format.

        Args:
            shift: Shift from database

        Returns:
            Shift in legacy format with all field name variants
        """
        return {
            # Primary fields
            'ID': shift['id'],
            'id': shift['id'],
            'Date': str(shift['date']) if shift['date'] else '',
            'date': str(shift['date']) if shift['date'] else '',
            'shift_date': str(shift['date']) if shift['date'] else '',
            'Employee ID': shift['employee_id'],
            'employee_id': shift['employee_id'],
            'Employee Name': shift['employee_name'],
            'employee_name': shift['employee_name'],

            # Time fields
            'Clock in': str(shift['clock_in']) if shift['clock_in'] else '',
            'clock_in': str(shift['clock_in']) if shift['clock_in'] else '',
            'Clock out': str(shift['clock_out']) if shift['clock_out'] else '',
            'clock_out': str(shift['clock_out']) if shift['clock_out'] else '',
            'Worked hours': float(shift['worked_hours'] or 0),
            'worked_hours': float(shift['worked_hours'] or 0),

            # Financial fields
            'Total sales': float(shift['total_sales'] or 0),
            'total_sales': float(shift['total_sales'] or 0),
            'Net sales': float(shift['net_sales'] or 0),
            'net_sales': float(shift['net_sales'] or 0),

            # Commission fields
            '%': float(shift['commission_pct'] or 0),
            'CommissionPct': float(shift['commission_pct'] or 0),
            'commission_pct': float(shift['commission_pct'] or 0),
            'total_commission_pct': float(shift['commission_pct'] or 0),

            # Earnings fields
            'Total per hour': float(shift['total_hourly'] or 0),
            'Total hourly': float(shift['total_hourly'] or 0),
            'total_per_hour': float(shift['total_hourly'] or 0),
            'total_hourly': float(shift['total_hourly'] or 0),
            'Commissions': float(shift['commissions'] or 0),
            'commissions': float(shift['commissions'] or 0),
            'commission_amount': float(shift['commissions'] or 0),
            'Total made': float(shift['total_made'] or 0),
            'total_made': float(shift['total_made'] or 0),

            # Rolling average fields
            'Rolling Average': float(shift['rolling_average'] or 0) if shift.get('rolling_average') else None,
            'rolling_average': float(shift['rolling_average'] or 0) if shift.get('rolling_average') else None,
            'Bonus Counter': shift.get('bonus_counter', False),
            'bonus_counter': shift.get('bonus_counter', False),
        }
