"""Bonus management methods for PostgresService."""

import logging
from typing import Dict, List, Optional
from decimal import Decimal

logger = logging.getLogger(__name__)


class BonusMixin:
    """Active bonuses CRUD and bonus settings."""

    def get_active_bonuses(self, employee_id: int) -> List[Dict]:
        """Get active (unapplied) bonuses for an employee in SheetsService format."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            cursor.execute("""
                SELECT * FROM active_bonuses
                WHERE employee_id = %s AND applied = FALSE
                ORDER BY created_at ASC
            """, (employee_id,))
            bonuses = cursor.fetchall()

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
            self._put_conn(conn)

    def create_bonus(
        self,
        employee_id: int,
        bonus_type: str,
        value: Decimal,
        created_at: str = None,
        shift_id: int = None
    ) -> int:
        """Create a new bonus."""
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
            logger.info(f"Created bonus {bonus_id} for employee {employee_id}: {bonus_type} ({value})")
            return bonus_id
        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to create bonus: {e}")
            raise
        finally:
            cursor.close()
            self._put_conn(conn)

    def apply_bonus(self, bonus_id: int, shift_id: int, cursor=None) -> None:
        """Apply a bonus to a shift."""
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

            if own_connection:
                conn.commit()

            logger.info(f"Applied bonus {bonus_id} to shift {shift_id}")

            if self.cache_manager:
                self.cache_manager.invalidate_key('shift_bonuses', shift_id)
        except Exception as e:
            if own_connection:
                conn.rollback()
            logger.error(f"Failed to apply bonus: {e}")
            raise
        finally:
            if own_connection:
                cursor.close()
                self._put_conn(conn)

    def get_shift_applied_bonuses(self, shift_id: int) -> List[Dict]:
        """Get bonuses applied to a shift in SheetsService format."""
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

            result = []
            for bonus in bonuses:
                result.append({
                    'BonusType': bonus['bonus_type'],
                    'BonusPct': float(bonus['value']),
                    'ShiftID': bonus['shift_id'],
                })

            if self.cache_manager:
                self.cache_manager.set('shift_bonuses', shift_id, result, ttl=600)

            return result
        finally:
            cursor.close()
            self._put_conn(conn)

    def get_bonus_setting(self, key: str) -> Optional[Decimal]:
        """Get bonus setting value."""
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
            self._put_conn(conn)
