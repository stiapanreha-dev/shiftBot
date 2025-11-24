"""Import ranks from Google Sheets to PostgreSQL.

This script fetches rank data from the "Ranks" sheet and populates
the PostgreSQL ranks table with the correct data.
"""
import psycopg2
from psycopg2 import extras
from config import Config
from sheets_service import SheetsService

def main():
    """Import ranks from Google Sheets."""
    # Fetch from Google Sheets
    sheets = SheetsService()
    sheets_ranks = sheets.get_ranks()

    if not sheets_ranks:
        print("❌ No ranks found in Google Sheets")
        return

    print(f"✓ Found {len(sheets_ranks)} ranks in Google Sheets")

    # Connect to PostgreSQL
    conn = psycopg2.connect(**Config.get_db_params(), cursor_factory=extras.RealDictCursor)
    cursor = conn.cursor()

    try:
        # Clear existing employee_ranks first (due to foreign key)
        cursor.execute('DELETE FROM employee_ranks')
        print('✓ Cleared existing employee_ranks from PostgreSQL')

        # Clear existing ranks
        cursor.execute('DELETE FROM ranks')
        print('✓ Cleared existing ranks from PostgreSQL')

        # Insert ranks from Sheets
        for idx, rank in enumerate(sheets_ranks, 1):
            rank_name = rank.get("Rank Name", "")
            min_amount = float(rank.get("Min Amount", 0))
            max_amount = float(rank.get("Max Amount", 999999))
            emoji = rank.get("Emoji", "")
            text = rank.get("TEXT", "")

            cursor.execute("""
                INSERT INTO ranks (
                    name, min_amount, max_amount, emoji, text,
                    display_order, is_active
                )
                VALUES (%s, %s, %s, %s, %s, %s, true)
            """, (
                rank_name,
                min_amount,
                max_amount,
                emoji,
                text,
                idx
            ))

            print(f"✓ Imported: {rank_name} ({emoji}) ${min_amount:.0f} - ${max_amount:.0f}")

        conn.commit()
        print(f"\n✅ Successfully imported {len(sheets_ranks)} ranks from Google Sheets to PostgreSQL")

        # Verify
        cursor.execute('SELECT name, min_amount, max_amount, emoji FROM ranks ORDER BY display_order')
        db_ranks = cursor.fetchall()

        print("\n📊 Ranks in PostgreSQL database:")
        for rank in db_ranks:
            print(f"  {rank['emoji']} {rank['name']}: ${rank['min_amount']:.0f} - ${rank['max_amount']:.0f}")

    except Exception as e:
        conn.rollback()
        print(f'❌ Error: {e}')
        raise
    finally:
        cursor.close()
        conn.close()

if __name__ == '__main__':
    main()
