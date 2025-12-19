"""Employee repository for employee data access."""

import logging
from decimal import Decimal
from typing import Optional, List, Dict

from .base import BaseRepository

logger = logging.getLogger(__name__)


class EmployeeRepository(BaseRepository):
    """Repository for employee CRUD operations."""

    DEFAULT_HOURLY_WAGE = Decimal('15.0')
    DEFAULT_COMMISSION = Decimal('8.0')

    def create(
        self,
        telegram_id: int,
        name: str,
        hourly_wage: Decimal = None,
        sales_commission: Decimal = None,
        is_active: bool = True
    ) -> int:
        """Create new employee.

        Args:
            telegram_id: Telegram user ID (used as primary key)
            name: Employee name
            hourly_wage: Hourly wage rate
            sales_commission: Base commission percentage
            is_active: Whether employee is active

        Returns:
            Employee ID (same as telegram_id)
        """
        hourly_wage = hourly_wage or self.DEFAULT_HOURLY_WAGE
        sales_commission = sales_commission or self.DEFAULT_COMMISSION

        query = """
            INSERT INTO employees (id, telegram_id, name, hourly_wage, sales_commission, is_active)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (id) DO NOTHING
            RETURNING id
        """
        result = self._execute_insert(query, (
            telegram_id, telegram_id, name,
            hourly_wage, sales_commission, is_active
        ))

        if result:
            logger.info(f"Created employee {telegram_id}: {name}")
        return result or telegram_id

    def get_by_id(self, employee_id: int) -> Optional[Dict]:
        """Get employee by ID (telegram_id).

        Args:
            employee_id: Employee telegram ID

        Returns:
            Employee data or None
        """
        query = "SELECT * FROM employees WHERE id = %s OR telegram_id = %s"
        return self._execute_one(query, (employee_id, employee_id))

    def get_settings(self, employee_id: int) -> Optional[Dict]:
        """Get employee settings in legacy format.

        Args:
            employee_id: Employee telegram ID

        Returns:
            Settings dict in legacy format or None
        """
        employee = self.get_by_id(employee_id)
        if not employee:
            return None

        hourly_wage = float(employee['hourly_wage']) if employee['hourly_wage'] else float(self.DEFAULT_HOURLY_WAGE)
        sales_commission = float(employee['sales_commission']) if employee['sales_commission'] else float(self.DEFAULT_COMMISSION)

        return {
            'Employee ID': employee['telegram_id'],
            'employee_id': employee['telegram_id'],
            'Employee Name': employee['name'],
            'employee_name': employee['name'],
            'Hourly wage': hourly_wage,
            'hourly_wage': hourly_wage,
            'Sales commission': sales_commission,
            'sales_commission': sales_commission,
            'BaseCommissionPct': Decimal(str(sales_commission)),
            'base_commission_pct': Decimal(str(sales_commission)),
            'is_active': employee['is_active'],
        }

    def get_or_create(
        self,
        telegram_id: int,
        name: str = "Unknown"
    ) -> Dict:
        """Get employee or create if not exists.

        Args:
            telegram_id: Telegram user ID
            name: Employee name (used if creating)

        Returns:
            Employee settings dict
        """
        settings = self.get_settings(telegram_id)
        if settings:
            return settings

        self.create(telegram_id, name)
        return self.get_settings(telegram_id)

    def update(
        self,
        employee_id: int,
        name: Optional[str] = None,
        hourly_wage: Optional[Decimal] = None,
        sales_commission: Optional[Decimal] = None,
        is_active: Optional[bool] = None
    ) -> bool:
        """Update employee fields.

        Args:
            employee_id: Employee telegram ID
            name: New name
            hourly_wage: New hourly wage
            sales_commission: New commission rate
            is_active: New active status

        Returns:
            True if updated
        """
        updates = []
        params = []

        if name is not None:
            updates.append("name = %s")
            params.append(name)

        if hourly_wage is not None:
            updates.append("hourly_wage = %s")
            params.append(hourly_wage)

        if sales_commission is not None:
            updates.append("sales_commission = %s")
            params.append(sales_commission)

        if is_active is not None:
            updates.append("is_active = %s")
            params.append(is_active)

        if not updates:
            return False

        updates.append("updated_at = now()")
        params.append(employee_id)

        query = f"UPDATE employees SET {', '.join(updates)} WHERE id = %s OR telegram_id = %s"
        params.append(employee_id)

        affected = self._execute_update(query, tuple(params))
        return affected > 0

    def get_all(self, active_only: bool = True) -> List[Dict]:
        """Get all employees.

        Args:
            active_only: Whether to return only active employees

        Returns:
            List of employees
        """
        if active_only:
            query = "SELECT * FROM employees WHERE is_active = true ORDER BY name"
        else:
            query = "SELECT * FROM employees ORDER BY name"
        return self._execute_many(query)

    def get_tier(self, employee_id: int) -> Optional[Dict]:
        """Get employee's commission tier.

        Args:
            employee_id: Employee telegram ID

        Returns:
            Tier dict with 'name' and 'percentage' or None
        """
        query = """
            SELECT bc.id, bc.name, bc.percentage, bc.min_sales, bc.max_sales
            FROM employees e
            JOIN base_commissions bc ON e.base_commission_id = bc.id
            WHERE e.id = %s OR e.telegram_id = %s
        """
        return self._execute_one(query, (employee_id, employee_id))

    def update_tier(self, employee_id: int, tier_id: int) -> bool:
        """Update employee's commission tier.

        Args:
            employee_id: Employee telegram ID
            tier_id: New tier ID

        Returns:
            True if updated
        """
        query = """
            UPDATE employees
            SET base_commission_id = %s,
                last_tier_update = CURRENT_DATE,
                updated_at = now()
            WHERE id = %s OR telegram_id = %s
        """
        affected = self._execute_update(query, (tier_id, employee_id, employee_id))
        return affected > 0

    def get_rank(self, employee_id: int, year: int, month: int) -> Optional[Dict]:
        """Get employee rank for specific month.

        Args:
            employee_id: Employee telegram ID
            year: Year
            month: Month (1-12)

        Returns:
            Rank record or None
        """
        query = """
            SELECT er.*, r.name as rank_name, r.emoji, r.text as rank_text
            FROM employee_ranks er
            LEFT JOIN ranks r ON er.current_rank_id = r.id
            WHERE er.employee_id = %s
              AND er.year = %s
              AND er.month = %s
        """
        return self._execute_one(query, (employee_id, year, month))

    def exists(self, employee_id: int) -> bool:
        """Check if employee exists.

        Args:
            employee_id: Employee telegram ID

        Returns:
            True if exists
        """
        query = "SELECT 1 FROM employees WHERE id = %s OR telegram_id = %s"
        result = self._execute_one(query, (employee_id, employee_id))
        return result is not None
