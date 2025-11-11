"""Check Shark rank bonuses in Google Sheets."""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

import logging
from sheets_service import SheetsService

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def check_shark_rank():
    """Check Shark rank bonuses in Google Sheets."""
    try:
        sheets = SheetsService()
        ranks = sheets.get_ranks()

        print("\n" + "="*60)
        print("🔍 CHECKING SHARK RANK IN GOOGLE SHEETS")
        print("="*60 + "\n")

        for rank in ranks:
            rank_name = rank.get("Rank Name", "")
            if rank_name == "Shark":
                print(f"✅ Found Shark rank:")
                print(f"   Rank Name: {rank_name}")
                print(f"   Min Amount: {rank.get('Min Amount')}")
                print(f"   Max Amount: {rank.get('Max Amount')}")
                print(f"   Emoji: {rank.get('Emoji')}")
                print(f"   Bonus 1: {rank.get('Bonus 1')}")
                print(f"   Bonus 2: {rank.get('Bonus 2')} 🎯")
                print(f"   Bonus 3: {rank.get('Bonus 3')}")

                bonus2 = rank.get('Bonus 2')
                if bonus2 == 'paid_day_off':
                    print("\n✅ Bonus 2 is correct: 'paid_day_off'")
                else:
                    print(f"\n❌ ERROR: Bonus 2 is '{bonus2}', expected 'paid_day_off'")

                return

        print("❌ Shark rank not found in Google Sheets!")

    except Exception as e:
        print(f"❌ Error: {e}")
        logger.error(f"Failed to check Shark rank: {e}")


if __name__ == "__main__":
    check_shark_rank()
