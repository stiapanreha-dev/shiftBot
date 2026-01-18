#!/usr/bin/env python3
"""Run HUSH coin migrations on PostgreSQL database."""

import os
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

import psycopg2
from config import DB_CONFIG


def run_migrations():
    """Run all HUSH coin migrations in order."""
    migrations_dir = Path(__file__).parent
    migration_files = sorted([
        f for f in migrations_dir.glob("*.sql")
        if f.name.startswith(("001", "002", "003", "004"))
    ])

    conn = psycopg2.connect(**DB_CONFIG)
    conn.autocommit = True
    cursor = conn.cursor()

    print("Running HUSH coin migrations...")
    print("=" * 50)

    for migration_file in migration_files:
        print(f"\n>>> Running: {migration_file.name}")
        try:
            sql = migration_file.read_text()
            cursor.execute(sql)

            # Fetch and print any results (verification queries)
            if cursor.description:
                rows = cursor.fetchall()
                for row in rows:
                    print(f"    {row}")

            print(f"    OK")
        except Exception as e:
            print(f"    ERROR: {e}")
            conn.close()
            sys.exit(1)

    conn.close()
    print("\n" + "=" * 50)
    print("All migrations completed successfully!")


if __name__ == "__main__":
    run_migrations()
