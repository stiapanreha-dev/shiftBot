"""Bonus repository for bonus data access."""

import logging
from decimal import Decimal
from typing import Optional, List, Dict

from .base import BaseRepository

logger = logging.getLogger(__name__)


class BonusRepository(BaseRepository):
    """Repository for bonus CRUD operations."""

    def create(
        self,
        employee_id: int,
        bonus_type: str,
        value: Decimal,
        applied: bool = False,
        shift_id: Optional[int] = None
    ) -> int:
        """Create new bonus.

        Args:
            employee_id: Employee telegram ID
            bonus_type: Type of bonus (percent_next, flat, double_commission, etc.)
            value: Bonus value
            applied: Whether bonus is already applied
            shift_id: Shift ID if applied

        Returns:
            New bonus ID
        """
        query = """
            INSERT INTO active_bonuses (employee_id, bonus_type, value, applied, shift_id)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id
        """
        bonus_id = self._execute_insert(query, (
            employee_id, bonus_type, value, applied, shift_id
        ))
        logger.info(f"Created bonus {bonus_id} for employee {employee_id}: {bonus_type}={value}")
        return bonus_id

    def get_by_id(self, bonus_id: int) -> Optional[Dict]:
        """Get bonus by ID.

        Args:
            bonus_id: Bonus ID

        Returns:
            Bonus data or None
        """
        query = "SELECT * FROM active_bonuses WHERE id = %s"
        return self._execute_one(query, (bonus_id,))

    def get_active(self, employee_id: int) -> List[Dict]:
        """Get active (not applied) bonuses for employee.

        Args:
            employee_id: Employee telegram ID

        Returns:
            List of active bonuses in legacy format
        """
        query = """
            SELECT * FROM active_bonuses
            WHERE employee_id = %s AND applied = false
            ORDER BY created_at ASC
        """
        bonuses = self._execute_many(query, (employee_id,))
        return [self._to_legacy_format(b) for b in bonuses]

    def get_applied_for_shift(self, shift_id: int) -> List[Dict]:
        """Get bonuses applied to specific shift.

        Args:
            shift_id: Shift ID

        Returns:
            List of applied bonuses in legacy format
        """
        query = """
            SELECT * FROM active_bonuses
            WHERE shift_id = %s AND applied = true
            ORDER BY applied_at ASC
        """
        bonuses = self._execute_many(query, (shift_id,))
        return [self._to_legacy_format(b) for b in bonuses]

    def apply(self, bonus_id: int, shift_id: int) -> bool:
        """Mark bonus as applied to shift.

        Args:
            bonus_id: Bonus ID
            shift_id: Shift ID

        Returns:
            True if updated
        """
        query = """
            UPDATE active_bonuses
            SET applied = true,
                shift_id = %s,
                applied_at = now()
            WHERE id = %s AND applied = false
        """
        affected = self._execute_update(query, (shift_id, bonus_id))

        if affected > 0:
            logger.info(f"Applied bonus {bonus_id} to shift {shift_id}")
            return True
        return False

    def apply_multiple(self, bonus_ids: List[int], shift_id: int) -> int:
        """Mark multiple bonuses as applied to shift.

        Args:
            bonus_ids: List of bonus IDs
            shift_id: Shift ID

        Returns:
            Number of bonuses applied
        """
        if not bonus_ids:
            return 0

        applied_count = 0
        for bonus_id in bonus_ids:
            if self.apply(bonus_id, shift_id):
                applied_count += 1

        return applied_count

    def get_all_for_employee(self, employee_id: int) -> List[Dict]:
        """Get all bonuses (active and applied) for employee.

        Args:
            employee_id: Employee telegram ID

        Returns:
            List of all bonuses
        """
        query = """
            SELECT * FROM active_bonuses
            WHERE employee_id = %s
            ORDER BY created_at DESC
        """
        bonuses = self._execute_many(query, (employee_id,))
        return [self._to_legacy_format(b) for b in bonuses]

    def delete(self, bonus_id: int) -> bool:
        """Delete bonus by ID.

        Args:
            bonus_id: Bonus ID

        Returns:
            True if deleted
        """
        query = "DELETE FROM active_bonuses WHERE id = %s"
        affected = self._execute_update(query, (bonus_id,))
        return affected > 0

    def delete_unapplied(self, employee_id: int) -> int:
        """Delete all unapplied bonuses for employee.

        Args:
            employee_id: Employee telegram ID

        Returns:
            Number of deleted bonuses
        """
        query = "DELETE FROM active_bonuses WHERE employee_id = %s AND applied = false"
        return self._execute_update(query, (employee_id,))

    def _to_legacy_format(self, bonus: Dict) -> Dict:
        """Convert bonus to legacy SheetsService format.

        Args:
            bonus: Bonus from database

        Returns:
            Bonus in legacy format
        """
        return {
            'ID': bonus['id'],
            'id': bonus['id'],
            'Employee ID': bonus['employee_id'],
            'employee_id': bonus['employee_id'],
            'Bonus Type': bonus['bonus_type'],
            'bonus_type': bonus['bonus_type'],
            'Value': float(bonus['value']) if bonus['value'] else 0,
            'value': float(bonus['value']) if bonus['value'] else 0,
            'Applied': bonus['applied'],
            'applied': bonus['applied'],
            'Shift ID': bonus['shift_id'],
            'shift_id': bonus['shift_id'],
            'Applied At': str(bonus['applied_at']) if bonus.get('applied_at') else None,
            'applied_at': str(bonus['applied_at']) if bonus.get('applied_at') else None,
            'Created At': str(bonus['created_at']) if bonus.get('created_at') else None,
            'created_at': str(bonus['created_at']) if bonus.get('created_at') else None,
        }
