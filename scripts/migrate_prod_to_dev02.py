#!/usr/bin/env python3
"""Migration script: PROD → dev-02 schema.

This script:
1. Renames shifts.total_per_hour → total_hourly
2. Creates bonus_settings table
3. Creates employee_fortnights table
4. Adds missing sync triggers
5. Updates add_to_sync_queue function
6. Resets all sequences to match actual data (after pg_dump import)

Full migration scenario:
    1. Backup PROD: pg_dump -U alex12060_user -d alex12060 > backup.sql
    2. Restore to local: psql -d alex12060 < backup.sql
    3. Run migration: python3 scripts/migrate_prod_to_dev02.py
    4. Backfill fortnights: python3 scripts/backfill_fortnights.py
    5. Recalculate tiers: python3 scripts/recalculate_employee_tiers.py

Usage:
    python3 migrate_prod_to_dev02.py [--dry-run]

Date: 2026-01-15
"""

import argparse
import sys


MIGRATION_SQL = """
-- =============================================================================
-- Migration: PROD → dev-02 schema
-- Date: 2026-01-15
-- =============================================================================

BEGIN;

-- -----------------------------------------------------------------------------
-- Step 1: Rename total_per_hour → total_hourly
-- -----------------------------------------------------------------------------
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'shifts' AND column_name = 'total_per_hour'
    ) THEN
        ALTER TABLE shifts RENAME COLUMN total_per_hour TO total_hourly;
        RAISE NOTICE '[OK] Renamed total_per_hour → total_hourly';
    ELSE
        RAISE NOTICE '[SKIP] Column total_per_hour does not exist (already renamed?)';
    END IF;
END $$;

-- -----------------------------------------------------------------------------
-- Step 2: Create bonus_settings table
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS bonus_settings (
    id SERIAL PRIMARY KEY,
    setting_key VARCHAR(50) UNIQUE NOT NULL,
    setting_value DECIMAL(10,4) NOT NULL,
    description TEXT,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT now(),
    updated_at TIMESTAMP DEFAULT now()
);

-- Insert default settings
INSERT INTO bonus_settings (setting_key, setting_value, description)
VALUES
    ('bonus_counter_percentage', 0.01, 'Percentage bonus for achieving rolling average target (1%)')
ON CONFLICT (setting_key) DO NOTHING;

DO $$ BEGIN RAISE NOTICE '[OK] bonus_settings table created/updated'; END $$;

-- -----------------------------------------------------------------------------
-- Step 3: Create employee_fortnights table
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS employee_fortnights (
    id SERIAL PRIMARY KEY,
    employee_id BIGINT REFERENCES employees(id),
    year INT NOT NULL,
    month INT NOT NULL CHECK (month BETWEEN 1 AND 12),
    fortnight INT NOT NULL CHECK (fortnight IN (1, 2)),
    total_shifts INT DEFAULT 0,
    total_worked_hours DECIMAL(10,2) DEFAULT 0,
    total_sales DECIMAL(12,2) DEFAULT 0,
    total_commissions DECIMAL(10,2) DEFAULT 0,
    total_hourly_pay DECIMAL(10,2) DEFAULT 0,
    total_made DECIMAL(10,2) DEFAULT 0,
    bonus_counter_true_count INT DEFAULT 0,
    bonus_amount DECIMAL(10,2) DEFAULT 0,
    total_salary DECIMAL(10,2) DEFAULT 0,
    payment_date DATE,
    is_paid BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT now(),
    updated_at TIMESTAMP DEFAULT now(),
    UNIQUE (employee_id, year, month, fortnight)
);

-- Index for efficient lookups
CREATE INDEX IF NOT EXISTS idx_employee_fortnights_lookup
ON employee_fortnights(employee_id, year, month, fortnight);

DO $$ BEGIN RAISE NOTICE '[OK] employee_fortnights table created'; END $$;

-- -----------------------------------------------------------------------------
-- Step 4: Add sync trigger for employee_fortnights
-- -----------------------------------------------------------------------------
DROP TRIGGER IF EXISTS trigger_sync_employee_fortnights ON employee_fortnights;
CREATE TRIGGER trigger_sync_employee_fortnights
    AFTER INSERT OR UPDATE OR DELETE ON employee_fortnights
    FOR EACH ROW EXECUTE FUNCTION add_to_sync_queue();

DO $$ BEGIN RAISE NOTICE '[OK] Sync trigger for employee_fortnights created'; END $$;

-- -----------------------------------------------------------------------------
-- Step 5: Update add_to_sync_queue function to handle employee_fortnights
-- -----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION add_to_sync_queue() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
DECLARE
    op VARCHAR(10);
    rec_data JSONB;
    rec_id BIGINT;
BEGIN
    -- Determine operation type
    IF TG_OP = 'DELETE' THEN
        op := 'DELETE';
        rec_data := row_to_json(OLD)::JSONB;
        rec_id := OLD.id;
    ELSIF TG_OP = 'UPDATE' THEN
        op := 'UPDATE';
        rec_data := row_to_json(NEW)::JSONB;
        rec_id := NEW.id;
    ELSIF TG_OP = 'INSERT' THEN
        op := 'INSERT';
        rec_data := row_to_json(NEW)::JSONB;
        rec_id := NEW.id;
    END IF;

    -- Insert into sync queue with priority
    INSERT INTO sync_queue (table_name, record_id, operation, data, priority)
    VALUES (
        TG_TABLE_NAME,
        rec_id,
        op,
        rec_data,
        CASE TG_TABLE_NAME
            WHEN 'shifts' THEN 1
            WHEN 'active_bonuses' THEN 2
            WHEN 'employee_ranks' THEN 3
            WHEN 'employee_fortnights' THEN 4
            ELSE 5
        END
    );

    RETURN NEW;
END;
$$;

DO $$ BEGIN RAISE NOTICE '[OK] add_to_sync_queue function updated'; END $$;

-- -----------------------------------------------------------------------------
-- Step 6: Reset all sequences to match actual data
-- -----------------------------------------------------------------------------
-- This is needed after importing data from pg_dump/pg_restore
DO $$
DECLARE
    seq_name TEXT;
    table_name TEXT;
    max_val BIGINT;
    seq_record RECORD;
BEGIN
    FOR seq_record IN
        SELECT
            s.relname AS seq_name,
            t.relname AS table_name,
            a.attname AS column_name
        FROM pg_class s
        JOIN pg_depend d ON d.objid = s.oid
        JOIN pg_class t ON d.refobjid = t.oid
        JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = d.refobjsubid
        WHERE s.relkind = 'S'
    LOOP
        EXECUTE format('SELECT COALESCE(MAX(%I), 0) FROM %I', seq_record.column_name, seq_record.table_name) INTO max_val;
        IF max_val > 0 THEN
            EXECUTE format('SELECT setval(%L, %s)', seq_record.seq_name, max_val + 1);
            RAISE NOTICE '[OK] Reset sequence % to %', seq_record.seq_name, max_val + 1;
        END IF;
    END LOOP;
END $$;

COMMIT;

-- =============================================================================
-- Migration complete
-- =============================================================================
DO $$ BEGIN RAISE NOTICE ''; END $$;
DO $$ BEGIN RAISE NOTICE '==========================================='; END $$;
DO $$ BEGIN RAISE NOTICE 'MIGRATION COMPLETED SUCCESSFULLY'; END $$;
DO $$ BEGIN RAISE NOTICE '==========================================='; END $$;
"""


def main():
    parser = argparse.ArgumentParser(description='Migrate PROD to dev-02 schema')
    parser.add_argument('--dry-run', action='store_true', help='Print SQL without executing')
    args = parser.parse_args()

    if args.dry_run:
        print("=" * 70)
        print("DRY RUN - SQL that would be executed:")
        print("=" * 70)
        print(MIGRATION_SQL)
        return 0

    # Execute migration
    try:
        import psycopg2
        import os

        conn = psycopg2.connect(
            host=os.getenv('DB_HOST', 'localhost'),
            port=int(os.getenv('DB_PORT', 5432)),
            database=os.getenv('DB_NAME', 'alex12060'),
            user=os.getenv('DB_USER', 'alex12060_user'),
            password=os.getenv('DB_PASSWORD', 'alex12060_pass')
        )
        conn.autocommit = True

        print("=" * 70)
        print("EXECUTING MIGRATION")
        print("=" * 70)

        cur = conn.cursor()
        cur.execute(MIGRATION_SQL)

        # Print any notices
        for notice in conn.notices:
            print(notice.strip())

        conn.close()
        print("\nMigration completed successfully!")
        return 0

    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
