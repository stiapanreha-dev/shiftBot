"""Shift sync processor."""

import logging
from typing import List, Optional, Any

from psycopg2.extras import RealDictCursor

from .base_processor import BaseSyncProcessor

logger = logging.getLogger(__name__)

# Which DB product fills which Shifts-sheet column. Product names change
# (performers are renamed), ids are stable. Adding a model = add the column
# to the sheet, extend SHEET_MODEL_SLOTS and map the new product id here.
PRODUCT_ID_TO_SLOT = {
    1: 'a',   # Chloe   -> ModelA
    2: 'b',   # Eva     -> ModelB
    3: 'c',   # Kat     -> ModelC
    9: 'd',   # Kiki    -> ModelD
    11: 'e',  # Model E -> ModelE
    12: 'f',  # Logan   -> ModelF
}
SHEET_MODEL_SLOTS = 'abcdef'  # sheet columns ModelA..ModelF, in order


class ShiftSyncProcessor(BaseSyncProcessor):
    """Processor for syncing shifts to Google Sheets."""

    @property
    def worksheet_name(self) -> str:
        return 'Shifts'

    @property
    def table_name(self) -> str:
        return 'shifts'

    @property
    def last_column(self) -> str:
        return 'U'  # 21 columns (added Model F - Logan)

    def fetch_record(self, record_id: int) -> Optional[dict]:
        """Fetch shift with product data from PostgreSQL."""
        with self.db_conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT
                    s.id,
                    s.date,
                    s.employee_id,
                    s.employee_name,
                    s.clock_in,
                    s.clock_out,
                    s.worked_hours,
                    s.total_sales,
                    s.net_sales,
                    s.commission_pct,
                    s.total_hourly,
                    s.commissions,
                    s.total_made,
                    s.rolling_average,
                    s.bonus_counter
                FROM shifts s
                WHERE s.id = %s
            """, (record_id,))
            record = cur.fetchone()
            if not record:
                return None

            for slot in SHEET_MODEL_SLOTS:
                record[f'model_{slot}'] = 0

            cur.execute("""
                SELECT sp.product_id, p.name, sp.amount
                FROM shift_products sp
                JOIN products p ON p.id = sp.product_id
                WHERE sp.shift_id = %s
            """, (record_id,))
            for row in cur.fetchall():
                slot = PRODUCT_ID_TO_SLOT.get(row['product_id'])
                if slot is None:
                    if row['amount']:
                        logger.warning(
                            f"Shift {record_id}: product '{row['name']}' "
                            f"(id={row['product_id']}) has no Shifts-sheet column "
                            "— add it to PRODUCT_ID_TO_SLOT"
                        )
                    continue
                record[f'model_{slot}'] = row['amount']
            return record

    def format_row(self, record: dict) -> List[Any]:
        """Format shift for Google Sheets.

        Columns: ID, Date, EmployeeID, EmployeeName, ClockIn, ClockOut, WorkedHours,
                 TotalSales, NetSales, CommissionPct, TotalHourly, Commissions, TotalMade,
                 RollingAverage, BonusCounter, ModelA, ModelB, ModelC, ModelD, ModelE, ModelF
        """
        f = self._safe_float
        dt = self._format_dt
        return [
            record['id'],
            dt(record['date']),
            record['employee_id'],
            record['employee_name'],
            dt(record['clock_in']),
            dt(record['clock_out']),
            f(record['worked_hours']),
            f(record['total_sales']),
            f(record['net_sales']),
            f(record['commission_pct']),
            f(record['total_hourly']),
            f(record['commissions']),
            f(record['total_made']),
            f(record['rolling_average']),
            self._bool_str(record['bonus_counter']),
        ] + [f(record[f'model_{slot}']) for slot in SHEET_MODEL_SLOTS]
