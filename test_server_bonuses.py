#!/usr/bin/env python3
"""Quick test for server bonuses."""

from sheets_service import SheetsService
from rank_service import RankService

sheets = SheetsService()
rs = RankService(sheets)
ranks = sheets.get_ranks()

print("\n🔍 Checking special bonuses on server:\n")

for rank in ranks:
    rank_name = rank.get("Rank Name", "")
    if rank_name in ["Shark", "King of Greed"]:
        emoji = rank.get("Emoji", "")
        print(f"{rank_name} {emoji}:")

        for i in range(1, 4):
            bonus_key = f"Bonus {i}"
            bonus_code = rank.get(bonus_key, "")
            if bonus_code and bonus_code != "none":
                desc = rs._format_bonus_description(bonus_code)
                marker = " 🎯" if bonus_code in ["paid_day_off", "telegram_premium"] else ""
                print(f"  {i}. {desc}{marker}")
        print()

print("✅ Done")
