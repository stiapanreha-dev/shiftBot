"""Shift management methods for PostgresService."""

import logging
from typing import Dict, List, Optional
from decimal import Decimal
from datetime import datetime

from psycopg2 import sql

from services.formatters import DateFormatter

logger = logging.getLogger(__name__)

# Lazy import to avoid circular dependency
_commission_calculator = None


def _get_calculator():
    global _commission_calculator
    if _commission_calculator is None:
        from services.calculators import CommissionCalculator
        _commission_calculator = CommissionCalculator()
    return _commission_calculator


class ShiftMixin:
    """Shift CRUD operations."""

    def get_next_id(self) -> int:
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT nextval('shifts_id_seq')")
            next_id = cursor.fetchone()['nextval']
            conn.rollback()
            return next_id
        finally:
            cursor.close()
            self._put_conn(conn)

    def create_shift(self, shift_data: Dict) -> int:
        """Create a new shift with products."""
        conn = self._get_conn()
        cursor = conn.cursor()
        calculator = _get_calculator()

        try:
            employee_id = shift_data['employee_id']
            employee_name = shift_data['employee_name']

            if 'clock_in' in shift_data:
                clock_in = shift_data['clock_in']
                clock_out = shift_data.get('clock_out')
                shift_date = clock_in.split()[0] if clock_in else shift_data.get('date', '')
            else:
                shift_date = shift_data['shift_date']
                time_in = shift_data['time_in']
                time_out = shift_data.get('time_out')
                clock_in = f"{shift_date} {time_in}:00"
                clock_out = f"{shift_date} {time_out}:00" if time_out else None

            products = shift_data.get('products', {})
            if 'total_sales' in shift_data:
                total_sales = Decimal(str(shift_data['total_sales']))
            else:
                total_sales = sum(Decimal(str(amount)) for amount in products.values())

            if 'total_hours' in shift_data:
                worked_hours = Decimal(str(shift_data['total_hours']))
            elif clock_in and clock_out:
                fmt = "%Y/%m/%d %H:%M:%S"
                dt_in = datetime.strptime(clock_in, fmt)
                dt_out = datetime.strptime(clock_out, fmt)
                hours = (dt_out - dt_in).total_seconds() / 3600
                worked_hours = Decimal(str(hours))
            else:
                worked_hours = Decimal('0')

            net_sales = Decimal(str(shift_data.get('net_sales', total_sales * Decimal('0.8'))))
            shift_date_normalized = DateFormatter.to_db_date(shift_date)

            settings = self.get_employee_settings(employee_id)
            if settings is None:
                self._create_employee_from_shift(employee_id, employee_name)
                settings = self.get_employee_settings(employee_id)
            hourly_wage = Decimal(str(settings.get("Hourly wage", 15.0)))

            base_commission_pct = Decimal(str(settings.get("Sales commission", 6.0)))
            active_bonuses = self.get_active_bonuses(employee_id) if clock_out else []

            calc_result = calculator.calculate(
                total_sales=total_sales,
                worked_hours=worked_hours,
                hourly_wage=hourly_wage,
                base_commission_pct=base_commission_pct,
                active_bonuses=active_bonuses,
                apply_bonuses=bool(clock_out)
            )

            commission_pct = calc_result.commission_pct
            applied_bonus_ids = calc_result.applied_bonus_ids
            total_hourly = Decimal(str(shift_data.get('total_per_hour', worked_hours * hourly_wage)))
            commissions = Decimal(str(shift_data.get('commission_amount', calc_result.commissions)))
            total_made = Decimal(str(shift_data.get('total_made', calc_result.total_made)))

            rolling_average = self.calculate_rolling_average(employee_id, shift_date_normalized)
            bonus_counter = self.calculate_bonus_counter(total_sales, rolling_average)

            cursor.execute("""
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
                    FALSE
                )
                RETURNING id
            """, (
                shift_date_normalized, employee_id, employee_name,
                clock_in, clock_out, worked_hours,
                total_sales, net_sales, commission_pct,
                total_hourly, commissions, total_made,
                rolling_average, bonus_counter
            ))

            shift_id = cursor.fetchone()['id']

            for bonus_id in applied_bonus_ids:
                if bonus_id:
                    self.apply_bonus(bonus_id, shift_id, cursor=cursor)
                    logger.info(f"Marked bonus {bonus_id} as applied to shift {shift_id}")

            products_to_insert = {
                name: Decimal(str(amt)) for name, amt in products.items()
                if Decimal(str(amt)) > 0
            }
            if products_to_insert:
                product_names = list(products_to_insert.keys())
                cursor.execute(
                    "SELECT id, name FROM products WHERE name IN %s",
                    (tuple(product_names),)
                )
                product_id_map = {row['name']: row['id'] for row in cursor.fetchall()}

                for product_name, amount_decimal in products_to_insert.items():
                    pid = product_id_map.get(product_name)
                    if pid:
                        cursor.execute("""
                            INSERT INTO shift_products (shift_id, product_id, amount)
                            VALUES (%s, %s, %s)
                            ON CONFLICT (shift_id, product_id) DO UPDATE
                            SET amount = EXCLUDED.amount
                        """, (shift_id, pid, amount_decimal))
                    else:
                        logger.warning(f"Product '{product_name}' not found in database")

            conn.commit()

            try:
                shift_dt = datetime.strptime(shift_date_normalized, "%Y-%m-%d").date()
                fortnight_num = self.get_fortnight_number(shift_dt.day)
                self.update_fortnight_totals(employee_id, shift_dt.year, shift_dt.month, fortnight_num)
            except Exception as e:
                logger.warning(f"Failed to update fortnight totals: {e}")

            logger.info(f"Created shift {shift_id} for employee {employee_id} (commission: {base_commission_pct}%, rolling_avg: {rolling_average}, bonus_counter: {bonus_counter})")
            return shift_id

        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to create shift: {e}")
            raise
        finally:
            cursor.close()
            self._put_conn(conn)

    def _shift_row_to_dict(self, shift: Dict, product_rows: list = None) -> Dict:
        """Convert a shift DB row + products to SheetsService format dict."""
        total_hourly_val = float(shift.get('total_hourly') or shift.get('total_per_hour') or 0)

        result = {
            'ShiftID': shift['id'],
            'ID': shift['id'],
            'shift_id': shift['id'],
            'Date': str(shift['date']),
            'shift_date': str(shift['date']),
            'EmployeeId': shift['employee_id'],
            'employee_id': shift['employee_id'],
            'EmployeeName': shift['employee_name'],
            'employee_name': shift['employee_name'],
            'Clock in': shift['clock_in'].strftime('%H:%M') if shift['clock_in'] else '',
            'time_in': shift['clock_in'].strftime('%H:%M') if shift['clock_in'] else '',
            'Clock out': shift['clock_out'].strftime('%H:%M') if shift['clock_out'] else '',
            'time_out': shift['clock_out'].strftime('%H:%M') if shift['clock_out'] else '',
            'Worked hours/shift': float(shift['worked_hours']) if shift['worked_hours'] else 0,
            'total_hours': float(shift['worked_hours']) if shift['worked_hours'] else 0,
            'Total sales': float(shift['total_sales']),
            'total_sales': float(shift['total_sales']),
            'Net sales': float(shift['net_sales']),
            'net_sales': float(shift['net_sales']),
            '%': float(shift['commission_pct']),
            'CommissionPct': float(shift['commission_pct']),
            'commission_pct': float(shift['commission_pct']),
            'total_commission_pct': float(shift['commission_pct']),
            'Total per hour': total_hourly_val,
            'total_per_hour': total_hourly_val,
            'Total hourly': total_hourly_val,
            'total_hourly': total_hourly_val,
            'Commissions': float(shift['commissions']),
            'commissions': float(shift['commissions']),
            'commission_amount': float(shift['commissions']),
            'Total made': float(shift['total_made']),
            'total_made': float(shift['total_made']),
            'rolling_average': float(shift['rolling_average']) if shift.get('rolling_average') else None,
            'Rolling Average': float(shift['rolling_average']) if shift.get('rolling_average') else None,
            'bonus_counter': bool(shift.get('bonus_counter', False)),
            'Bonus Counter': bool(shift.get('bonus_counter', False)),
        }

        all_products = self.get_products()
        for product_name in all_products:
            result[product_name] = 0
            result[f"{product_name.lower()}_sales"] = 0

        if product_rows:
            for product_row in product_rows:
                product_name = product_row['name']
                amount = float(product_row['amount'])
                result[product_name] = amount
                result[f"{product_name.lower()}_sales"] = amount

        return result

    def get_shift_by_id(self, shift_id: int) -> Optional[Dict]:
        """Get shift data by ID with product sales in SheetsService format."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT * FROM shifts WHERE id = %s", (shift_id,))
            shift = cursor.fetchone()
            if not shift:
                return None

            cursor.execute("""
                SELECT p.name, sp.amount
                FROM shift_products sp
                JOIN products p ON sp.product_id = p.id
                WHERE sp.shift_id = %s
            """, (shift_id,))
            products = cursor.fetchall()
            return self._shift_row_to_dict(shift, products)
        finally:
            cursor.close()
            self._put_conn(conn)

    def find_row_by_id(self, shift_id: int) -> Optional[int]:
        """Find shift row by ID (for compatibility)."""
        shift = self.get_shift_by_id(shift_id)
        return shift_id if shift else None

    def update_shift_field(self, shift_id: int, field: str, value: str) -> bool:
        """Update a single field of a shift."""
        conn = self._get_conn()
        cursor = conn.cursor()

        field_mapping = {
            'Clock in': 'clock_in',
            'Clock out': 'clock_out',
            'Worked hours/shift': 'worked_hours',
            'Total sales': 'total_sales',
            'Net sales': 'net_sales',
            '%': 'commission_pct',
            'CommissionPct': 'commission_pct',
            'Total per hour': 'total_hourly',
            'total_per_hour': 'total_hourly',
            'Total hourly': 'total_hourly',
            'Commissions': 'commissions',
            'Total made': 'total_made',
            'rolling_average': 'rolling_average',
            'bonus_counter': 'bonus_counter',
        }

        pg_field = field_mapping.get(field)
        if pg_field is None:
            raise ValueError(f"Unknown shift field: '{field}'. Allowed: {list(field_mapping.keys())}")

        try:
            if pg_field in ['clock_in', 'clock_out']:
                full_datetime = DateFormatter.to_db_datetime(value)
                cursor.execute(
                    sql.SQL("UPDATE shifts SET {} = %s, updated_at = now() WHERE id = %s").format(
                        sql.Identifier(pg_field)
                    ),
                    (full_datetime, shift_id)
                )
            else:
                cursor.execute(
                    sql.SQL("UPDATE shifts SET {} = %s, updated_at = now() WHERE id = %s").format(
                        sql.Identifier(pg_field)
                    ),
                    (value, shift_id)
                )

            conn.commit()
            logger.info(f"Updated shift {shift_id}: {pg_field} = {value}")

            if self.cache_manager:
                self.cache_manager.invalidate_key('shift', shift_id)

            return True

        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to update shift field: {e}")
            return False
        finally:
            cursor.close()
            self._put_conn(conn)

    def recalculate_worked_hours(self, shift_id: int) -> bool:
        """Recalculate worked_hours, total_hourly, total_made based on clock_in/clock_out."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "SELECT clock_in, clock_out, commissions, employee_id FROM shifts WHERE id = %s",
                (shift_id,)
            )
            shift = cursor.fetchone()
            if not shift or not shift['clock_in'] or not shift['clock_out']:
                return False

            clock_in = shift['clock_in']
            clock_out = shift['clock_out']
            commissions = shift['commissions'] or Decimal('0')
            employee_id = shift['employee_id']

            diff = clock_out - clock_in
            worked_hours = Decimal(str(diff.total_seconds() / 3600))
            worked_hours = worked_hours.quantize(Decimal('0.01'))

            settings = self.get_employee_settings(employee_id)
            hourly_wage = Decimal(str(settings.get("Hourly wage", 15.0))) if settings else Decimal('15.0')

            total_hourly = worked_hours * hourly_wage
            total_made = total_hourly + commissions

            cursor.execute("""
                UPDATE shifts
                SET worked_hours = %s,
                    total_hourly = %s,
                    total_made = %s,
                    updated_at = now()
                WHERE id = %s
            """, (worked_hours, total_hourly, total_made, shift_id))

            conn.commit()
            logger.info(f"Recalculated shift {shift_id}: {worked_hours}h, ${total_hourly}/h, total=${total_made}")

            if self.cache_manager:
                self.cache_manager.invalidate_key('shift', shift_id)

            return True

        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to recalculate worked_hours: {e}")
            return False
        finally:
            cursor.close()
            self._put_conn(conn)

    def update_total_sales(self, shift_id: int, total_sales: Decimal) -> bool:
        """Update total sales for a shift."""
        conn = self._get_conn()
        cursor = conn.cursor()
        calculator = _get_calculator()

        try:
            cursor.execute("SELECT commission_pct, worked_hours, employee_id, date FROM shifts WHERE id = %s", (shift_id,))
            shift = cursor.fetchone()
            if not shift:
                return False

            commission_pct = shift['commission_pct']
            worked_hours = shift['worked_hours'] or Decimal('1')
            employee_id = shift['employee_id']
            shift_date = shift['date']

            settings = self.get_employee_settings(employee_id)
            hourly_wage = Decimal(str(settings.get("Hourly wage", 15.0))) if settings else Decimal('15.0')

            calc_result = calculator.recalculate_from_existing(
                total_sales=total_sales,
                worked_hours=worked_hours,
                hourly_wage=hourly_wage,
                existing_commission_pct=commission_pct
            )

            net_sales = calculator.calculate_net_sales(total_sales)
            commissions = calc_result.commissions
            total_hourly = worked_hours * hourly_wage
            total_made = calc_result.total_made

            shift_date_str = str(shift_date)
            rolling_average = self.calculate_rolling_average(employee_id, shift_date_str)
            bonus_counter = self.calculate_bonus_counter(total_sales, rolling_average)

            cursor.execute("""
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
            """, (total_sales, net_sales, commissions, total_hourly, total_made, rolling_average, bonus_counter, shift_id))

            conn.commit()
            logger.info(f"Updated total_sales for shift {shift_id}: {total_sales}")

            try:
                fortnight_num = self.get_fortnight_number(shift_date.day)
                self.update_fortnight_totals(employee_id, shift_date.year, shift_date.month, fortnight_num)
            except Exception as e:
                logger.warning(f"Failed to update fortnight totals: {e}")

            if self.cache_manager:
                self.cache_manager.invalidate_key('shift', shift_id)
                self.cache_manager.invalidate_key('shift_bonuses', shift_id)

            return True

        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to update total_sales: {e}")
            return False
        finally:
            cursor.close()
            self._put_conn(conn)

    def _fetch_shifts_with_products(self, where_clause: str, params: tuple) -> List[Dict]:
        """Fetch shifts with products in a single query (no N+1)."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            cursor.execute(f"""
                SELECT s.*, p.name as product_name, sp.amount as product_amount
                FROM shifts s
                LEFT JOIN shift_products sp ON sp.shift_id = s.id
                LEFT JOIN products p ON sp.product_id = p.id
                {where_clause}
            """, params)

            rows = cursor.fetchall()
            if not rows:
                return []

            shifts_map = {}
            for row in rows:
                sid = row['id']
                if sid not in shifts_map:
                    shifts_map[sid] = {'shift': row, 'products': []}
                if row['product_name'] and row['product_amount']:
                    shifts_map[sid]['products'].append({
                        'name': row['product_name'],
                        'amount': row['product_amount'],
                    })

            return [
                self._shift_row_to_dict(data['shift'], data['products'])
                for data in shifts_map.values()
            ]
        finally:
            cursor.close()
            self._put_conn(conn)

    def get_last_shifts(self, employee_id: int, limit: int = 3) -> List[Dict]:
        """Get last N shifts for an employee."""
        return self._fetch_shifts_with_products(
            "WHERE s.employee_id = %s ORDER BY s.date DESC, s.clock_in DESC LIMIT %s",
            (employee_id, limit)
        )

    def get_all_shifts(self) -> List[Dict]:
        """Get all shifts."""
        return self._fetch_shifts_with_products(
            "ORDER BY s.date DESC, s.clock_in DESC",
            ()
        )

    def get_models_from_shift(self, shift: Dict) -> List[str]:
        """Get list of product names that have sales in this shift."""
        models = []
        all_products = self.get_products()
        for product in all_products:
            if shift.get(product, 0) > 0 or shift.get(f"{product.lower()}_sales", 0) > 0:
                models.append(product)
        return models

    def find_previous_shift_with_models(
        self,
        employee_id: int,
        shift_date: str,
        time_in: str,
        models: List[str]
    ) -> Optional[Dict]:
        """Find previous shift with specified models."""
        if not models:
            return None

        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            current_timestamp = f"{shift_date} {time_in}:00"
            placeholders = ','.join(['%s'] * len(models))
            cursor.execute(f"""
                SELECT id FROM products WHERE name IN ({placeholders})
            """, models)
            product_ids = [row['id'] for row in cursor.fetchall()]
            if not product_ids:
                return None

            product_placeholders = ','.join(['%s'] * len(product_ids))
            query = f"""
                SELECT s.id, s.clock_in
                FROM shifts s
                JOIN shift_products sp ON s.id = sp.shift_id
                WHERE s.employee_id = %s
                AND s.clock_in < %s
                AND sp.product_id IN ({product_placeholders})
                AND sp.amount > 0
                ORDER BY s.clock_in DESC
                LIMIT 1
            """
            cursor.execute(query, [employee_id, current_timestamp] + product_ids)
            result = cursor.fetchone()
            if result:
                return self.get_shift_by_id(result['id'])
            return None
        finally:
            cursor.close()
            self._put_conn(conn)

    def find_shifts_with_model(
        self,
        employee_id: int,
        shift_date: str,
        time_in: str,
        model: str,
        days_back: int = 30
    ) -> List[Dict]:
        """Find shifts with a specific model within N days back."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            current_timestamp = f"{shift_date} {time_in}:00"
            cutoff_date = datetime.strptime(shift_date, "%Y-%m-%d").date()

            cursor.execute("SELECT id FROM products WHERE name = %s", (model,))
            product = cursor.fetchone()
            if not product:
                return []

            product_id = product['id']
            query = """
                SELECT s.id, s.clock_in
                FROM shifts s
                JOIN shift_products sp ON s.id = sp.shift_id
                WHERE s.employee_id = %s
                AND s.date >= %s - INTERVAL '%s days'
                AND s.clock_in < %s
                AND sp.product_id = %s
                AND sp.amount > 0
                ORDER BY s.clock_in DESC
            """
            cursor.execute(query, (employee_id, cutoff_date, days_back, current_timestamp, product_id))
            shift_ids = cursor.fetchall()

            result = []
            for row in shift_ids:
                shift = self.get_shift_by_id(row['id'])
                if shift:
                    result.append(shift)
            return result
        finally:
            cursor.close()
            self._put_conn(conn)
