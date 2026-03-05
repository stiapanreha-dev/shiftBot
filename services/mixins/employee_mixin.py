"""Employee management methods for PostgresService."""

import logging
from typing import Dict, Optional
from decimal import Decimal

logger = logging.getLogger(__name__)


class EmployeeMixin:
    """Employee CRUD operations."""

    def get_employee_settings(self, employee_id: int) -> Optional[Dict]:
        """Get employee settings in SheetsService format."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            cursor.execute("""
                SELECT * FROM employees WHERE telegram_id = %s AND is_active = TRUE
            """, (employee_id,))
            employee = cursor.fetchone()
            if not employee:
                return None

            hourly_wage = float(employee['hourly_wage']) if employee['hourly_wage'] else 15.0
            sales_commission = float(employee['sales_commission']) if employee['sales_commission'] else 6.0

            return {
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
        finally:
            cursor.close()
            self._put_conn(conn)

    def create_default_employee_settings(self, employee_id: int) -> None:
        """Create default employee settings."""
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

            if self.cache_manager:
                self.cache_manager.invalidate_key('employee_settings', employee_id)
        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to create default employee settings: {e}")
            raise
        finally:
            cursor.close()
            self._put_conn(conn)

    def _create_employee_from_shift(self, telegram_id: int, name: str) -> None:
        """Auto-create employee record from shift data."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            cursor.execute("""
                INSERT INTO employees (id, name, telegram_id, is_active, sales_commission)
                VALUES (%s, %s, %s, TRUE, 6.0)
                ON CONFLICT (id) DO NOTHING
            """, (telegram_id, name, telegram_id))
            conn.commit()
            logger.info(f"Auto-created employee: {name} (telegram_id={telegram_id}, commission=6.0%)")

            if self.cache_manager:
                self.cache_manager.invalidate_key('employee_settings', telegram_id)
        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to auto-create employee: {e}")
            raise
        finally:
            cursor.close()
            self._put_conn(conn)
