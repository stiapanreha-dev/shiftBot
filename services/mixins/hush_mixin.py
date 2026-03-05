"""HUSH coin methods for PostgresService."""

import logging
from typing import Dict, List, Optional
from decimal import Decimal

logger = logging.getLogger(__name__)


class HushMixin:
    """HUSH coin balance, transactions, and rewards."""

    def get_hush_balance(self, employee_id: int) -> Decimal:
        """Get HUSH coin balance for employee."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            cursor.execute("""
                SELECT COALESCE(hush_balance, 0) as balance
                FROM employees
                WHERE id = %s OR telegram_id = %s
            """, (employee_id, employee_id))
            result = cursor.fetchone()
            return Decimal(str(result['balance'])) if result else Decimal('0')
        finally:
            cursor.close()
            self._put_conn(conn)

    def add_hush_coins(
        self,
        employee_id: int,
        amount: int,
        transaction_type: str,
        description: str,
        rank_id: int = None
    ) -> int:
        """Add HUSH coins to employee balance."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            cursor.execute("""
                SELECT id, COALESCE(hush_balance, 0) as balance
                FROM employees
                WHERE id = %s OR telegram_id = %s
            """, (employee_id, employee_id))
            result = cursor.fetchone()
            if not result:
                raise ValueError(f"Employee {employee_id} not found")

            emp_id = result['id']
            current_balance = Decimal(str(result['balance']))
            new_balance = current_balance + Decimal(amount)

            cursor.execute("""
                UPDATE employees
                SET hush_balance = %s, updated_at = now()
                WHERE id = %s
            """, (new_balance, emp_id))

            cursor.execute("""
                INSERT INTO hush_transactions
                (employee_id, amount, transaction_type, description, rank_id, balance_after)
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (emp_id, amount, transaction_type, description, rank_id, new_balance))

            transaction_id = cursor.fetchone()['id']
            conn.commit()

            logger.info(f"Added {amount} HUSH to employee {employee_id}. "
                       f"New balance: {new_balance}. TX ID: {transaction_id}")
            return transaction_id
        except Exception as e:
            conn.rollback()
            logger.error(f"Error adding HUSH coins: {e}")
            raise
        finally:
            cursor.close()
            self._put_conn(conn)

    def withdraw_hush_coins(
        self,
        employee_id: int,
        amount: int,
        description: str
    ) -> int:
        """Withdraw HUSH coins from employee balance."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            cursor.execute("""
                SELECT id, COALESCE(hush_balance, 0) as balance
                FROM employees
                WHERE id = %s OR telegram_id = %s
            """, (employee_id, employee_id))
            result = cursor.fetchone()
            if not result:
                raise ValueError(f"Employee {employee_id} not found")

            emp_id = result['id']
            current_balance = Decimal(str(result['balance']))

            if current_balance < amount:
                raise ValueError(
                    f"Insufficient HUSH balance. "
                    f"Current: {current_balance}, requested: {amount}"
                )

            new_balance = current_balance - Decimal(amount)

            cursor.execute("""
                UPDATE employees
                SET hush_balance = %s, updated_at = now()
                WHERE id = %s
            """, (new_balance, emp_id))

            cursor.execute("""
                INSERT INTO hush_transactions
                (employee_id, amount, transaction_type, description, balance_after)
                VALUES (%s, %s, 'withdrawal', %s, %s)
                RETURNING id
            """, (emp_id, -amount, description, new_balance))

            transaction_id = cursor.fetchone()['id']
            conn.commit()

            logger.info(f"Withdrawn {amount} HUSH from employee {employee_id}. "
                       f"New balance: {new_balance}. TX ID: {transaction_id}")
            return transaction_id
        except Exception as e:
            conn.rollback()
            logger.error(f"Error withdrawing HUSH coins: {e}")
            raise
        finally:
            cursor.close()
            self._put_conn(conn)

    def get_hush_transactions(
        self,
        employee_id: int,
        limit: int = 10
    ) -> List[Dict]:
        """Get HUSH transaction history for employee."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            cursor.execute("""
                SELECT ht.*, r.name as rank_name
                FROM hush_transactions ht
                LEFT JOIN ranks r ON r.id = ht.rank_id
                WHERE ht.employee_id = %s
                ORDER BY ht.created_at DESC
                LIMIT %s
            """, (employee_id, limit))
            return [dict(r) for r in cursor.fetchall()]
        finally:
            cursor.close()
            self._put_conn(conn)

    def get_hush_rank_rewards(self, rank_id: int) -> List[int]:
        """Get HUSH reward amounts for a rank."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            cursor.execute("""
                SELECT reward_amount
                FROM hush_rank_rewards
                WHERE rank_id = %s
                ORDER BY position
            """, (rank_id,))
            return [row['reward_amount'] for row in cursor.fetchall()]
        finally:
            cursor.close()
            self._put_conn(conn)

    def reset_monthly_hush_balances(self) -> int:
        """Reset hush_balance to 0 for all employees (monthly reset on 1st)."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            cursor.execute("""
                SELECT id, name, COALESCE(hush_balance, 0) as balance
                FROM employees
                WHERE hush_balance > 0 AND is_active = TRUE
            """)
            employees = cursor.fetchall()

            if not employees:
                logger.info("No employees with positive hush_balance to reset")
                return 0

            for emp in employees:
                cursor.execute("""
                    INSERT INTO hush_transactions
                    (employee_id, amount, transaction_type, description, balance_after)
                    VALUES (%s, %s, 'monthly_reset', 'Monthly balance reset', 0)
                """, (emp['id'], -emp['balance']))

            cursor.execute("""
                UPDATE employees
                SET hush_balance = 0, updated_at = now()
                WHERE hush_balance > 0 AND is_active = TRUE
            """)
            count = cursor.rowcount

            conn.commit()
            logger.info(f"Reset hush_balance for {count} employees")
            return count
        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to reset monthly hush balances: {e}")
            raise
        finally:
            cursor.close()
            self._put_conn(conn)
