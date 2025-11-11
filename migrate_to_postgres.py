#!/usr/bin/env python3
"""Migration script: Google Sheets → PostgreSQL.

This script migrates ALL data from Google Sheets to PostgreSQL:
1. Reference data: EmployeeSettings, DynamicRates, Ranks, EmployeeRanks
2. Transactional data: Shifts, ActiveBonuses

Features:
- Dry-run mode for safety
- Data validation
- Rollback on error
- Progress reporting
- Incremental sync support

Usage:
    # Dry run (default)
    python3 migrate_to_postgres.py --dry-run

    # Execute migration
    python3 migrate_to_postgres.py --execute

    # Specific tables only
    python3 migrate_to_postgres.py --execute --tables shifts,employee_settings

Author: Claude Code (PROMPT 4.1 - PostgreSQL Migration)
Date: 2025-11-11
Version: 3.0.0
"""

import argparse
import logging
import sys
from datetime import datetime
from typing import Dict, List, Any, Optional, Tuple
from decimal import Decimal
import psycopg2
from psycopg2 import extras

from sheets_service import SheetsService
from pg_schema import PostgresSchema, get_db_connection
from config import Config

logger = logging.getLogger(__name__)


class GoogleSheetsToPostgres:
    """Migrates data from Google Sheets to PostgreSQL."""

    def __init__(self, dry_run: bool = True):
        """Initialize migration.

        Args:
            dry_run: If True, don't commit changes to database
        """
        self.dry_run = dry_run
        self.sheets = SheetsService()
        self.pg_schema = PostgresSchema()
        self.stats = {
            'employee_settings': {'inserted': 0, 'updated': 0, 'errors': 0},
            'dynamic_rates': {'inserted': 0, 'updated': 0, 'errors': 0},
            'ranks': {'inserted': 0, 'updated': 0, 'errors': 0},
            'employee_ranks': {'inserted': 0, 'updated': 0, 'errors': 0},
            'shifts': {'inserted': 0, 'updated': 0, 'errors': 0},
            'active_bonuses': {'inserted': 0, 'updated': 0, 'errors': 0},
        }

        logger.info(f"Migration initialized (dry_run={dry_run})")

    def migrate_employee_settings(self, conn) -> Tuple[int, int]:
        """Migrate EmployeeSettings from Sheets to PostgreSQL.

        Returns:
            Tuple of (inserted, updated) counts
        """
        logger.info("Migrating EmployeeSettings...")

        # Get data from Sheets
        ws = self.sheets.spreadsheet.worksheet("EmployeeSettings")
        records = ws.get_all_records()

        cursor = conn.cursor()
        inserted = 0
        updated = 0

        for record in records:
            try:
                employee_id = int(record['EmployeeID'])
                employee_name = record['EmployeeName']
                base_commission = Decimal(str(record['BaseCommissionPct']))
                active = str(record.get('Active', 'TRUE')).upper() == 'TRUE'

                cursor.execute("""
                    INSERT INTO employee_settings
                        (employee_id, employee_name, base_commission_pct, active)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (employee_id) DO UPDATE SET
                        employee_name = EXCLUDED.employee_name,
                        base_commission_pct = EXCLUDED.base_commission_pct,
                        active = EXCLUDED.active,
                        updated_at = CURRENT_TIMESTAMP
                    RETURNING (xmax = 0) AS inserted
                """, (employee_id, employee_name, base_commission, active))

                result = cursor.fetchone()
                if result[0]:
                    inserted += 1
                else:
                    updated += 1

            except Exception as e:
                logger.error(f"Error migrating employee {record.get('EmployeeID')}: {e}")
                self.stats['employee_settings']['errors'] += 1

        self.stats['employee_settings']['inserted'] = inserted
        self.stats['employee_settings']['updated'] = updated

        logger.info(f"✓ EmployeeSettings: {inserted} inserted, {updated} updated")
        return inserted, updated

    def migrate_dynamic_rates(self, conn) -> Tuple[int, int]:
        """Migrate DynamicRates from Sheets to PostgreSQL.

        Returns:
            Tuple of (inserted, updated) counts
        """
        logger.info("Migrating DynamicRates...")

        ws = self.sheets.spreadsheet.worksheet("DynamicRates")
        records = ws.get_all_records()

        cursor = conn.cursor()

        # Clear existing rates (they're configuration data)
        cursor.execute("DELETE FROM dynamic_rates")

        inserted = 0

        for record in records:
            try:
                min_sales = Decimal(str(record['MinSales']))
                max_sales = Decimal(str(record['MaxSales'])) if record.get('MaxSales') else None
                rate_pct = Decimal(str(record['RatePct']))

                cursor.execute("""
                    INSERT INTO dynamic_rates (min_sales, max_sales, rate_pct)
                    VALUES (%s, %s, %s)
                """, (min_sales, max_sales, rate_pct))

                inserted += 1

            except Exception as e:
                logger.error(f"Error migrating rate: {e}")
                self.stats['dynamic_rates']['errors'] += 1

        self.stats['dynamic_rates']['inserted'] = inserted

        logger.info(f"✓ DynamicRates: {inserted} inserted")
        return inserted, 0

    def migrate_ranks(self, conn) -> Tuple[int, int]:
        """Migrate Ranks from Sheets to PostgreSQL.

        Returns:
            Tuple of (inserted, updated) counts
        """
        logger.info("Migrating Ranks...")

        ws = self.sheets.spreadsheet.worksheet("Ranks")
        records = ws.get_all_records()

        cursor = conn.cursor()
        inserted = 0
        updated = 0

        for record in records:
            try:
                rank_name = record['RankName']
                bonus_pct = Decimal(str(record['BonusPct']))
                min_total_sales = Decimal(str(record['MinTotalSales'])) if record.get('MinTotalSales') else None
                min_days_worked = int(record['MinDaysWorked']) if record.get('MinDaysWorked') else None
                description = record.get('Description', '')

                cursor.execute("""
                    INSERT INTO ranks
                        (rank_name, bonus_pct, min_total_sales, min_days_worked, description)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (rank_name) DO UPDATE SET
                        bonus_pct = EXCLUDED.bonus_pct,
                        min_total_sales = EXCLUDED.min_total_sales,
                        min_days_worked = EXCLUDED.min_days_worked,
                        description = EXCLUDED.description
                    RETURNING (xmax = 0) AS inserted
                """, (rank_name, bonus_pct, min_total_sales, min_days_worked, description))

                result = cursor.fetchone()
                if result[0]:
                    inserted += 1
                else:
                    updated += 1

            except Exception as e:
                logger.error(f"Error migrating rank {record.get('RankName')}: {e}")
                self.stats['ranks']['errors'] += 1

        self.stats['ranks']['inserted'] = inserted
        self.stats['ranks']['updated'] = updated

        logger.info(f"✓ Ranks: {inserted} inserted, {updated} updated")
        return inserted, updated

    def migrate_employee_ranks(self, conn) -> Tuple[int, int]:
        """Migrate EmployeeRanks from Sheets to PostgreSQL.

        Returns:
            Tuple of (inserted, updated) counts
        """
        logger.info("Migrating EmployeeRanks...")

        ws = self.sheets.spreadsheet.worksheet("EmployeeRanks")
        records = ws.get_all_records()

        cursor = conn.cursor()
        inserted = 0
        updated = 0

        for record in records:
            try:
                employee_id = int(record['EmployeeID'])
                month = record['Month']  # Format: YYYY-MM
                rank_name = record.get('RankName')

                if not rank_name:
                    continue

                # Get rank_id from rank_name
                cursor.execute("SELECT id FROM ranks WHERE rank_name = %s", (rank_name,))
                rank_result = cursor.fetchone()

                if not rank_result:
                    logger.warning(f"Rank '{rank_name}' not found, skipping employee {employee_id} for {month}")
                    continue

                rank_id = rank_result['id']

                cursor.execute("""
                    INSERT INTO employee_ranks (employee_id, month, rank_id)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (employee_id, month) DO UPDATE SET
                        rank_id = EXCLUDED.rank_id
                    RETURNING (xmax = 0) AS inserted
                """, (employee_id, month, rank_id))

                result = cursor.fetchone()
                if result[0]:
                    inserted += 1
                else:
                    updated += 1

            except Exception as e:
                logger.error(f"Error migrating employee rank: {e}")
                self.stats['employee_ranks']['errors'] += 1

        self.stats['employee_ranks']['inserted'] = inserted
        self.stats['employee_ranks']['updated'] = updated

        logger.info(f"✓ EmployeeRanks: {inserted} inserted, {updated} updated")
        return inserted, updated

    def migrate_shifts(self, conn) -> Tuple[int, int]:
        """Migrate Shifts from Sheets to PostgreSQL.

        This is the MAIN transactional data.

        Returns:
            Tuple of (inserted, updated) counts
        """
        logger.info("Migrating Shifts...")

        ws = self.sheets.spreadsheet.worksheet("Shifts")
        records = ws.get_all_records()

        cursor = conn.cursor()
        inserted = 0
        updated = 0

        total_records = len(records)
        logger.info(f"Found {total_records} shifts to migrate")

        for idx, record in enumerate(records, 1):
            if idx % 100 == 0:
                logger.info(f"Progress: {idx}/{total_records} shifts processed")

            try:
                shift_id = int(record['ShiftID'])
                employee_id = int(record['EmployeeID'])
                employee_name = record['EmployeeName']
                shift_date = record['Date']  # Format: YYYY-MM-DD
                time_in = record['TimeIn']  # Format: HH:MM
                time_out = record.get('TimeOut') or None
                total_hours = Decimal(str(record['TotalHours'])) if record.get('TotalHours') else None

                # Product sales
                bella_sales = Decimal(str(record.get('BellaSales', 0) or 0))
                laura_sales = Decimal(str(record.get('LauraSales', 0) or 0))
                sophie_sales = Decimal(str(record.get('SophieSales', 0) or 0))
                alice_sales = Decimal(str(record.get('AliceSales', 0) or 0))
                emma_sales = Decimal(str(record.get('EmmaSales', 0) or 0))
                molly_sales = Decimal(str(record.get('MollySales', 0) or 0))
                total_sales = Decimal(str(record.get('TotalSales', 0) or 0))

                # Commission breakdown
                base_commission_pct = Decimal(str(record.get('BaseCommissionPct', 0) or 0))
                dynamic_commission_pct = Decimal(str(record.get('DynamicCommissionPct', 0) or 0))
                bonus_commission_pct = Decimal(str(record.get('BonusCommissionPct', 0) or 0))
                total_commission_pct = Decimal(str(record.get('CommissionPct', 0) or 0))
                commission_amount = Decimal(str(record.get('CommissionAmount', 0) or 0))

                status = record.get('Status', 'active')

                cursor.execute("""
                    INSERT INTO shifts (
                        shift_id, employee_id, employee_name, shift_date, time_in, time_out, total_hours,
                        bella_sales, laura_sales, sophie_sales, alice_sales, emma_sales, molly_sales, total_sales,
                        base_commission_pct, dynamic_commission_pct, bonus_commission_pct,
                        total_commission_pct, commission_amount, status
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s, %s
                    )
                    ON CONFLICT (shift_id) DO UPDATE SET
                        employee_id = EXCLUDED.employee_id,
                        employee_name = EXCLUDED.employee_name,
                        shift_date = EXCLUDED.shift_date,
                        time_in = EXCLUDED.time_in,
                        time_out = EXCLUDED.time_out,
                        total_hours = EXCLUDED.total_hours,
                        bella_sales = EXCLUDED.bella_sales,
                        laura_sales = EXCLUDED.laura_sales,
                        sophie_sales = EXCLUDED.sophie_sales,
                        alice_sales = EXCLUDED.alice_sales,
                        emma_sales = EXCLUDED.emma_sales,
                        molly_sales = EXCLUDED.molly_sales,
                        total_sales = EXCLUDED.total_sales,
                        base_commission_pct = EXCLUDED.base_commission_pct,
                        dynamic_commission_pct = EXCLUDED.dynamic_commission_pct,
                        bonus_commission_pct = EXCLUDED.bonus_commission_pct,
                        total_commission_pct = EXCLUDED.total_commission_pct,
                        commission_amount = EXCLUDED.commission_amount,
                        status = EXCLUDED.status,
                        updated_at = CURRENT_TIMESTAMP
                    RETURNING (xmax = 0) AS inserted
                """, (
                    shift_id, employee_id, employee_name, shift_date, time_in, time_out, total_hours,
                    bella_sales, laura_sales, sophie_sales, alice_sales, emma_sales, molly_sales, total_sales,
                    base_commission_pct, dynamic_commission_pct, bonus_commission_pct,
                    total_commission_pct, commission_amount, status
                ))

                result = cursor.fetchone()
                if result[0]:
                    inserted += 1
                else:
                    updated += 1

            except Exception as e:
                logger.error(f"Error migrating shift {record.get('ShiftID')}: {e}")
                self.stats['shifts']['errors'] += 1

        self.stats['shifts']['inserted'] = inserted
        self.stats['shifts']['updated'] = updated

        logger.info(f"✓ Shifts: {inserted} inserted, {updated} updated")
        return inserted, updated

    def migrate_active_bonuses(self, conn) -> Tuple[int, int]:
        """Migrate ActiveBonuses from Sheets to PostgreSQL.

        Returns:
            Tuple of (inserted, updated) counts
        """
        logger.info("Migrating ActiveBonuses...")

        ws = self.sheets.spreadsheet.worksheet("ActiveBonuses")
        records = ws.get_all_records()

        cursor = conn.cursor()
        inserted = 0

        # Clear existing bonuses (they'll be re-inserted)
        cursor.execute("DELETE FROM active_bonuses")

        for record in records:
            try:
                shift_id = int(record['ShiftID'])
                bonus_type = record['BonusType']
                bonus_pct = Decimal(str(record['BonusPct']))
                reason = record.get('Reason', '')

                # Check if shift exists
                cursor.execute("SELECT 1 FROM shifts WHERE shift_id = %s", (shift_id,))
                if not cursor.fetchone():
                    logger.warning(f"Shift {shift_id} not found, skipping bonus")
                    continue

                cursor.execute("""
                    INSERT INTO active_bonuses (shift_id, bonus_type, bonus_pct, reason)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (shift_id, bonus_type) DO NOTHING
                """, (shift_id, bonus_type, bonus_pct, reason))

                inserted += 1

            except Exception as e:
                logger.error(f"Error migrating bonus: {e}")
                self.stats['active_bonuses']['errors'] += 1

        self.stats['active_bonuses']['inserted'] = inserted

        logger.info(f"✓ ActiveBonuses: {inserted} inserted")
        return inserted, 0

    def run_migration(self, tables: Optional[List[str]] = None) -> Dict[str, Any]:
        """Run full migration.

        Args:
            tables: List of table names to migrate, or None for all

        Returns:
            Migration statistics
        """
        all_tables = [
            'employee_settings',
            'dynamic_rates',
            'ranks',
            'employee_ranks',
            'shifts',
            'active_bonuses'
        ]

        tables_to_migrate = tables if tables else all_tables

        logger.info(f"Starting migration (dry_run={self.dry_run})")
        logger.info(f"Tables to migrate: {', '.join(tables_to_migrate)}")

        start_time = datetime.now()

        conn = self.pg_schema.get_connection()

        try:
            # Migrate tables in order (reference data first, then transactional)
            if 'employee_settings' in tables_to_migrate:
                self.migrate_employee_settings(conn)

            if 'dynamic_rates' in tables_to_migrate:
                self.migrate_dynamic_rates(conn)

            if 'ranks' in tables_to_migrate:
                self.migrate_ranks(conn)

            if 'employee_ranks' in tables_to_migrate:
                self.migrate_employee_ranks(conn)

            if 'shifts' in tables_to_migrate:
                self.migrate_shifts(conn)

            if 'active_bonuses' in tables_to_migrate:
                self.migrate_active_bonuses(conn)

            if self.dry_run:
                logger.info("DRY RUN: Rolling back all changes")
                conn.rollback()
            else:
                logger.info("Committing changes to database")
                conn.commit()

            end_time = datetime.now()
            duration = (end_time - start_time).total_seconds()

            logger.info(f"✅ Migration completed in {duration:.2f}s")
            self.print_stats()

            return {
                'success': True,
                'duration_seconds': duration,
                'stats': self.stats
            }

        except Exception as e:
            logger.error(f"Migration failed: {e}")
            conn.rollback()
            raise
        finally:
            conn.close()

    def print_stats(self):
        """Print migration statistics."""
        print("\n" + "=" * 60)
        print("MIGRATION STATISTICS")
        print("=" * 60)

        for table, stats in self.stats.items():
            inserted = stats['inserted']
            updated = stats['updated']
            errors = stats['errors']

            if inserted + updated + errors > 0:
                print(f"\n{table}:")
                print(f"  Inserted: {inserted}")
                print(f"  Updated:  {updated}")
                print(f"  Errors:   {errors}")

        print("\n" + "=" * 60)


def main():
    parser = argparse.ArgumentParser(
        description="Migrate data from Google Sheets to PostgreSQL"
    )
    parser.add_argument(
        '--execute',
        action='store_true',
        help='Execute migration (default is dry-run)'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        default=True,
        help='Dry run mode (default)'
    )
    parser.add_argument(
        '--tables',
        type=str,
        help='Comma-separated list of tables to migrate'
    )
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Enable verbose logging'
    )

    args = parser.parse_args()

    # Setup logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # Parse tables
    tables = None
    if args.tables:
        tables = [t.strip() for t in args.tables.split(',')]

    # Determine dry_run mode
    dry_run = not args.execute

    if dry_run:
        print("=" * 60)
        print("DRY RUN MODE - No changes will be committed")
        print("=" * 60)
    else:
        print("=" * 60)
        print("EXECUTING MIGRATION - Changes will be committed!")
        print("=" * 60)

    # Run migration
    migrator = GoogleSheetsToPostgres(dry_run=dry_run)

    try:
        migrator.run_migration(tables=tables)
    except Exception as e:
        logger.error(f"Migration failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
