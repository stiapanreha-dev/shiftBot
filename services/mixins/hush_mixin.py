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
        """Add HUSH coins to employee balance.

        The balance update is a single atomic UPDATE: a concurrent
        read-modify-write would silently lose one of the additions.
        """
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            cursor.execute("""
                UPDATE employees
                SET hush_balance = COALESCE(hush_balance, 0) + %s, updated_at = now()
                WHERE id = %s OR telegram_id = %s
                RETURNING id, hush_balance
            """, (Decimal(amount), employee_id, employee_id))
            result = cursor.fetchone()
            if not result:
                raise ValueError(f"Employee {employee_id} not found")

            emp_id = result['id']
            new_balance = Decimal(str(result['hush_balance']))

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
        """Withdraw HUSH coins from employee balance.

        Atomic UPDATE with a balance guard: two concurrent withdrawals can
        never overdraw the balance or lose each other's update.
        """
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            cursor.execute("""
                UPDATE employees
                SET hush_balance = COALESCE(hush_balance, 0) - %s, updated_at = now()
                WHERE (id = %s OR telegram_id = %s)
                  AND COALESCE(hush_balance, 0) >= %s
                RETURNING id, hush_balance
            """, (Decimal(amount), employee_id, employee_id, Decimal(amount)))
            result = cursor.fetchone()
            if not result:
                # Distinguish "no such employee" from "not enough coins"
                cursor.execute("""
                    SELECT COALESCE(hush_balance, 0) as balance
                    FROM employees
                    WHERE id = %s OR telegram_id = %s
                """, (employee_id, employee_id))
                row = cursor.fetchone()
                if not row:
                    raise ValueError(f"Employee {employee_id} not found")
                raise ValueError(
                    f"Insufficient HUSH balance. "
                    f"Current: {row['balance']}, requested: {amount}"
                )

            emp_id = result['id']
            new_balance = Decimal(str(result['hush_balance']))

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

    def has_monthly_reset_occurred(self, year: int, month: int) -> bool:
        """Check if monthly HUSH reset already happened for given year/month."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            cursor.execute("""
                SELECT EXISTS(
                    SELECT 1 FROM hush_transactions
                    WHERE transaction_type = 'monthly_reset'
                      AND EXTRACT(YEAR FROM created_at) = %s
                      AND EXTRACT(MONTH FROM created_at) = %s
                    LIMIT 1
                ) as already_reset
            """, (year, month))
            result = cursor.fetchone()
            return bool(result['already_reset']) if result else False
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
