#!/usr/bin/env python3
"""
Скрипт обновления тиров сотрудников.
Запускается 1 числа каждого месяца для пересчёта тиров по продажам прошлого месяца.

Cron: 0 0 1 * * /opt/alex12060-bot/venv/bin/python /opt/alex12060-bot/scripts/update_tiers.py

Тиры:
- Tier A: $100k-$300k → 4%
- Tier B: $50k-$100k → 5%
- Tier C: $0-$50k → 6% (default)
"""

import os
import sys
import logging
from datetime import datetime
from pathlib import Path

# Добавить корень проекта в path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Загрузить .env
from dotenv import load_dotenv
load_dotenv(project_root / '.env')

from services.postgres_service import PostgresService

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(project_root / 'logs' / 'tier_updates.log')
    ]
)
logger = logging.getLogger(__name__)


def get_previous_month():
    """Получить год и месяц для расчёта (прошлый месяц)."""
    now = datetime.now()
    if now.month == 1:
        return now.year - 1, 12
    return now.year, now.month - 1


def main():
    """Основная функция обновления тиров."""
    logger.info("=" * 60)
    logger.info("Запуск обновления тиров сотрудников")
    logger.info("=" * 60)

    try:
        # Получить прошлый месяц
        year, month = get_previous_month()
        logger.info(f"Расчёт тиров по продажам за {month:02d}/{year}")

        # Инициализировать сервис
        service = PostgresService()

        # Обновить тиры всех сотрудников
        results = service.update_all_employee_tiers(year, month)

        # Вывести результаты
        changed_count = 0
        for result in results:
            status = "ИЗМЕНЁН" if result['changed'] else "без изменений"
            logger.info(
                f"  {result['employee_name']}: "
                f"${result['total_sales']:,.0f} → {result['new_tier']} ({result['new_percentage']}%) "
                f"[{status}]"
            )
            if result['changed']:
                changed_count += 1

        logger.info("-" * 60)
        logger.info(f"Всего сотрудников: {len(results)}")
        logger.info(f"Изменено тиров: {changed_count}")
        logger.info("=" * 60)

        return 0

    except Exception as e:
        logger.error(f"Ошибка обновления тиров: {e}", exc_info=True)
        return 1


if __name__ == '__main__':
    sys.exit(main())
