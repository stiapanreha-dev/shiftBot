"""Populate ranks table with default data.

This script adds the standard rank tiers to the PostgreSQL database.
"""
import psycopg2
from psycopg2 import extras
from config import Config

# Rank data based on standard commission system
ranks_data = [
    {
        'name': 'Rookie',
        'min_amount': 0,
        'max_amount': 4999.99,
        'text': 'Welcome! This is where everyone starts. Focus on learning the basics and building your skills.',
        'display_order': 1
    },
    {
        'name': 'Hustler',
        'min_amount': 5000,
        'max_amount': 9999.99,
        'text': "You're making progress! Keep up the momentum and aim for consistency.",
        'display_order': 2
    },
    {
        'name': 'Closer',
        'min_amount': 10000,
        'max_amount': 14999.99,
        'text': "Strong performance! You're closing deals and building solid results.",
        'display_order': 3
    },
    {
        'name': 'Shark',
        'min_amount': 15000,
        'max_amount': 19999.99,
        'text': "Excellent work! You're a top performer driving serious revenue.",
        'display_order': 4
    },
    {
        'name': 'King of Greed',
        'min_amount': 20000,
        'max_amount': 29999.99,
        'text': "Outstanding! You're dominating the leaderboard and setting the standard.",
        'display_order': 5
    },
    {
        'name': 'Chatting God',
        'min_amount': 30000,
        'max_amount': 9999999.99,  # Max for NUMERIC(10,2)
        'text': "Legendary status! You're the absolute best, crushing all expectations.",
        'display_order': 6
    }
]

def main():
    """Populate ranks table."""
    conn = psycopg2.connect(**Config.get_db_params(), cursor_factory=extras.RealDictCursor)
    cursor = conn.cursor()

    try:
        # Clear existing ranks
        cursor.execute('DELETE FROM ranks')
        print('Cleared existing ranks')

        # Insert ranks
        for rank in ranks_data:
            cursor.execute("""
                INSERT INTO ranks (name, min_amount, max_amount, text, display_order, is_active)
                VALUES (%(name)s, %(min_amount)s, %(max_amount)s, %(text)s, %(display_order)s, true)
            """, rank)

        conn.commit()
        print(f'✓ Successfully inserted {len(ranks_data)} ranks')

        # Verify
        cursor.execute('SELECT name, min_amount, max_amount FROM ranks ORDER BY display_order')
        ranks = cursor.fetchall()
        print('\nRanks in database:')
        for rank in ranks:
            print(f'  {rank["name"]}: ${rank["min_amount"]:.0f} - ${rank["max_amount"]:.0f}')

    except Exception as e:
        conn.rollback()
        print(f'✗ Error: {e}')
        raise
    finally:
        cursor.close()
        conn.close()

if __name__ == '__main__':
    main()
