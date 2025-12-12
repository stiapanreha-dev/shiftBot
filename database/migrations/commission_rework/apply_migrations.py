#!/usr/bin/env python3
"""
Apply Commission Rework migrations to PostgreSQL database.

Usage:
    python apply_migrations.py [--dry-run] [--env DEV|PROD]

Environment variables:
    POSTGRES_HOST - Database host (default: localhost)
    POSTGRES_PORT - Database port (default: 5432)
    POSTGRES_DB - Database name (default: alex12060)
    POSTGRES_USER - Database user (default: alex12060_user)
    POSTGRES_PASSWORD - Database password
"""

import os
import sys
import argparse
import psycopg2
from psycopg2 import sql, extras
from pathlib import Path
from datetime import datetime

# Migration files in order
MIGRATIONS = [
    "001_create_base_commissions.sql",
    "002_create_bonus_settings.sql",
    "003_create_employee_fortnights.sql",
    "004_alter_employees.sql",
    "005_alter_shifts.sql",
    "006_deactivate_dynamic_rates.sql",
]


def get_connection(env: str = "DEV"):
    """Get database connection based on environment."""
    if env == "PROD":
        return psycopg2.connect(
            host="localhost",
            port=5432,
            database="alex12060",
            user="alex12060_user",
            password="alex12060_pass",
            cursor_factory=extras.RealDictCursor
        )
    else:  # DEV
        return psycopg2.connect(
            host=os.getenv("POSTGRES_HOST", "localhost"),
            port=int(os.getenv("POSTGRES_PORT", 5432)),
            database=os.getenv("POSTGRES_DB", "alex12060"),
            user=os.getenv("POSTGRES_USER", "lexun"),
            password=os.getenv("POSTGRES_PASSWORD", ""),
            cursor_factory=extras.RealDictCursor
        )


def create_migrations_table(cursor):
    """Create migrations tracking table if not exists."""
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS applied_migrations (
            id SERIAL PRIMARY KEY,
            filename VARCHAR(255) UNIQUE NOT NULL,
            applied_at TIMESTAMP DEFAULT now(),
            checksum VARCHAR(64)
        )
    """)


def get_applied_migrations(cursor) -> set:
    """Get set of already applied migration filenames."""
    cursor.execute("SELECT filename FROM applied_migrations")
    return {row['filename'] for row in cursor.fetchall()}


def apply_migration(cursor, filename: str, sql_content: str):
    """Apply a single migration."""
    cursor.execute(sql_content)
    cursor.execute(
        "INSERT INTO applied_migrations (filename) VALUES (%s)",
        (filename,)
    )


def main():
    parser = argparse.ArgumentParser(description="Apply Commission Rework migrations")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be done without applying")
    parser.add_argument("--env", choices=["DEV", "PROD"], default="DEV", help="Target environment")
    args = parser.parse_args()

    # Get migration directory
    migrations_dir = Path(__file__).parent

    print(f"=== Commission Rework Migration ===")
    print(f"Environment: {args.env}")
    print(f"Dry run: {args.dry_run}")
    print(f"Migrations dir: {migrations_dir}")
    print()

    try:
        conn = get_connection(args.env)
        cursor = conn.cursor()

        # Create tracking table
        create_migrations_table(cursor)
        conn.commit()

        # Get already applied migrations
        applied = get_applied_migrations(cursor)
        print(f"Already applied: {len(applied)} migrations")

        # Process each migration
        migrations_applied = 0
        migrations_skipped = 0

        for filename in MIGRATIONS:
            if filename in applied:
                print(f"  SKIP: {filename} (already applied)")
                migrations_skipped += 1
                continue

            filepath = migrations_dir / filename
            if not filepath.exists():
                print(f"  ERROR: {filename} not found!")
                continue

            sql_content = filepath.read_text()

            if args.dry_run:
                print(f"  WOULD APPLY: {filename}")
            else:
                print(f"  APPLYING: {filename}...", end=" ")
                try:
                    apply_migration(cursor, filename, sql_content)
                    conn.commit()
                    print("OK")
                    migrations_applied += 1
                except Exception as e:
                    conn.rollback()
                    print(f"ERROR: {e}")
                    raise

        print()
        print(f"=== Summary ===")
        print(f"Applied: {migrations_applied}")
        print(f"Skipped: {migrations_skipped}")
        print(f"Total migrations: {len(MIGRATIONS)}")

        if not args.dry_run and migrations_applied > 0:
            print()
            print("Migration completed successfully!")

    except Exception as e:
        print(f"Migration failed: {e}")
        sys.exit(1)
    finally:
        if 'conn' in locals():
            conn.close()


if __name__ == "__main__":
    main()
