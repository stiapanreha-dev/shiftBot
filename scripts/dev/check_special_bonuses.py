"""Check special bonuses (paid_day_off, telegram_premium) in Google Sheets."""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

import logging
from sheets_service import SheetsService
from rank_service import RankService

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def check_special_bonuses():
    """Check special bonuses for Shark and King of Greed ranks."""
    try:
        sheets = SheetsService()
        rank_service = RankService(sheets)
        ranks = sheets.get_ranks()

        print("\n" + "="*80)
        print("🔍 CHECKING SPECIAL BONUSES (paid_day_off & telegram_premium)")
        print("="*80 + "\n")

        target_ranks = ["Shark", "King of Greed"]

        for rank in ranks:
            rank_name = rank.get("Rank Name", "")

            if rank_name in target_ranks:
                print(f"{'─'*80}")
                print(f"🏆 {rank_name} {rank.get('Emoji', '')}")
                print(f"{'─'*80}")
                print(f"   Amount Range: ${int(rank.get('Min Amount', 0)):,} – ${int(rank.get('Max Amount', 0)):,}")
                print(f"\n   Bonuses:")

                bonuses = [
                    ("Bonus 1", rank.get("Bonus 1")),
                    ("Bonus 2", rank.get("Bonus 2")),
                    ("Bonus 3", rank.get("Bonus 3"))
                ]

                for idx, (label, bonus_code) in enumerate(bonuses, 1):
                    if bonus_code and bonus_code != "none":
                        description = rank_service._format_bonus_description(bonus_code)

                        # Highlight special bonuses
                        marker = ""
                        if bonus_code == "paid_day_off":
                            marker = " 🎯 (SPECIAL)"
                        elif bonus_code == "telegram_premium":
                            marker = " 🎯 (SPECIAL)"

                        print(f"   {idx}. {description}{marker}")
                        print(f"      Code: {bonus_code}")
                    else:
                        print(f"   {idx}. (none)")

                print()

        print("="*80)
        print("✅ All special bonuses checked")
        print("="*80 + "\n")

    except Exception as e:
        print(f"❌ Error: {e}")
        logger.error(f"Failed to check special bonuses: {e}")


if __name__ == "__main__":
    check_special_bonuses()
