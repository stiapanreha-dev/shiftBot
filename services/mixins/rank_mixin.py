"""Rank management methods for PostgresService."""

import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class RankMixin:
    """Rank queries, updates, and determination."""

    def get_ranks(self) -> List[Dict]:
        """Get all ranks in SheetsService format."""
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
            result = []
            for rank in ranks:
                cursor.execute("""
                    SELECT bonus_code FROM rank_bonuses
                    WHERE rank_id = %s
                    ORDER BY position ASC
                """, (rank['id'],))
                bonuses = cursor.fetchall()
                bonus_codes = [b['bonus_code'] for b in bonuses]

                result.append({
                    'id': rank['id'],
                    'ID': rank['id'],
                    'RankName': rank['name'],
                    'rank_name': rank['name'],
                    'BonusPct': 0,
                    'bonus_pct': 0,
                    'MinTotalSales': float(rank['min_amount']),
                    'min_total_sales': float(rank['min_amount']),
                    'MaxTotalSales': float(rank['max_amount']),
                    'max_total_sales': float(rank['max_amount']),
                    'Description': rank['text'] or '',
                    'description': rank['text'] or '',
                    'Emoji': rank.get('emoji') or '',
                    'emoji': rank.get('emoji') or '',
                    'Bonuses': ','.join(bonus_codes),
                })

            if self.cache_manager:
                self.cache_manager.set('ranks', 'all', result, ttl=900)

            return result
        finally:
            cursor.close()
            self._put_conn(conn)

    def get_employee_rank(self, employee_id: int, year: int, month: int) -> Optional[Dict]:
        """Get employee rank record for a specific month."""
        cache_key = f"{employee_id}_{year}_{month}"
        if self.cache_manager:
            cached = self.cache_manager.get('employee_rank', cache_key)
            if cached:
                return cached

        conn = self._get_conn()
        cursor = conn.cursor()
        try:
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

            rank_record = dict(result)

            if self.cache_manager:
                self.cache_manager.set('employee_rank', cache_key, rank_record, ttl=300)

            return rank_record
        finally:
            cursor.close()
            self._put_conn(conn)

    def update_employee_rank(
        self,
        employee_id: int,
        new_rank: str,
        year: int,
        month: int,
        last_updated: str = None,
        total_sales: float = None
    ) -> None:
        """Update employee rank for a month."""
        rank_name = new_rank
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT id FROM ranks WHERE name = %s", (rank_name,))
            rank = cursor.fetchone()
            if not rank:
                logger.error(f"Rank '{rank_name}' not found")
                return

            rank_id = rank['id']

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

            cursor.execute("""
                SELECT current_rank_id FROM employee_ranks
                WHERE employee_id = %s AND year = %s AND month = %s
            """, (employee_id, year, month))
            existing = cursor.fetchone()
            previous_rank_id = existing['current_rank_id'] if existing else None

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
            logger.info(f"Updated rank for employee {employee_id} ({year}-{month:02d}): {rank_name}, sales: ${total_sales:.2f}")

            if self.cache_manager:
                cache_key = f"{employee_id}_{year}_{month}"
                self.cache_manager.invalidate_key('employee_rank', cache_key)
        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to update employee rank: {e}")
            raise
        finally:
            cursor.close()
            self._put_conn(conn)

    def mark_rank_notified(self, employee_id: int, year: int, month: int) -> None:
        """Mark that employee was notified about rank change."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            cursor.execute("""
                UPDATE employee_ranks
                SET notified = TRUE, updated_at = NOW()
                WHERE employee_id = %s AND year = %s AND month = %s
            """, (employee_id, year, month))
            conn.commit()
            logger.info(f"Marked rank notified for employee {employee_id} ({year}-{month:02d})")

            if self.cache_manager:
                cache_key = f"{employee_id}_{year}_{month}"
                self.cache_manager.invalidate_key('employee_rank', cache_key)
        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to mark rank notified: {e}")
            raise
        finally:
            cursor.close()
            self._put_conn(conn)

    def determine_rank(self, employee_id: int, year: int, month: int) -> str:
        """Determine employee rank based on monthly total sales."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            month_val = f"{year}-{month:02d}"
            cursor.execute("""
                SELECT COALESCE(SUM(total_sales), 0) as total
                FROM shifts
                WHERE employee_id = %s
                  AND to_char(clock_in, 'YYYY-MM') = %s
            """, (employee_id, month_val))
            result = cursor.fetchone()
            total_sales = float(result['total']) if result else 0.0

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
            self._put_conn(conn)

    def get_rank_text(self, rank_name: str) -> str:
        """Get rank description text."""
        ranks = self.get_ranks()
        for rank in ranks:
            if rank['rank_name'] == rank_name:
                return rank['description']
        return ""

    def get_rank_bonuses(self, rank_name: str) -> List[str]:
        """Get bonus codes for a rank."""
        ranks = self.get_ranks()
        for rank in ranks:
            if rank['rank_name'] == rank_name:
                bonuses_str = rank.get('Bonuses', '')
                return [b.strip() for b in bonuses_str.split(',') if b.strip()]
        return []

    def get_rank_id_by_name(self, rank_name: str) -> Optional[int]:
        """Get rank ID by name."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            cursor.execute("""
                SELECT id FROM ranks WHERE name = %s AND is_active = TRUE
            """, (rank_name,))
            result = cursor.fetchone()
            return result['id'] if result else None
        finally:
            cursor.close()
            self._put_conn(conn)
