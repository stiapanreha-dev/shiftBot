# Test Suite for Telegram Shift Tracking Bot

Автоматизированные тесты для проверки функциональности бота.

## 📁 Структура тестов

```
tests/
├── integration/          # Интеграционные тесты (полные сценарии)
│   ├── test_scenario_2_1.py   # Тест: Создание смены с 1 продуктом
│   └── test_scenario_2_2.py   # Тест: Создание смены с несколькими продуктами
│
├── unit/                # Юнит-тесты (отдельные компоненты)
│   └── (future tests)
│
├── utils/               # Утилиты для тестирования
│   ├── delete_shifts.py       # Удаление смен из Google Sheets
│   └── check_today_shifts.py  # Проверка смен за сегодня
│
└── fixtures/            # Тестовые данные и фикстуры
    └── (future fixtures)
```

---

## 🧪 Интеграционные тесты (integration/)

Полные end-to-end тесты, имитирующие реальное взаимодействие пользователя с ботом.

### Запуск интеграционных тестов:

```bash
# Запустить все интеграционные тесты
python3 -m pytest tests/integration/

# Запустить конкретный тест
python3 tests/integration/test_scenario_2_1.py
python3 tests/integration/test_scenario_2_2.py
```

### Доступные тесты:

| Файл | Сценарий | Статус |
|------|----------|--------|
| `test_scenario_2_1.py` | Создание смены с 1 продуктом | ✅ PASS |
| `test_scenario_2_2.py` | Создание смены с несколькими продуктами | ✅ PASS |

---

## 🔬 Юнит-тесты (unit/)

Тесты отдельных функций и компонентов (будут добавлены в будущем).

---

## 🛠️ Утилиты (utils/)

Вспомогательные скрипты для тестирования.

### delete_shifts.py

Удаление смен из Google Sheets по ID.

**Использование:**
```bash
python3 tests/utils/delete_shifts.py 11 12 13
```

**Пример вывода:**
```
🗑️  Deleting shifts: [11, 12, 13]
  Shift 11 found at row 12
  Deleting row 12 (Shift ID: 11)
✅ Successfully deleted 3 shift(s)
📊 Remaining shifts in database: 10
```

### check_today_shifts.py

Проверка всех смен пользователя за сегодня.

**Использование:**
```bash
python3 tests/utils/check_today_shifts.py
```

**Пример вывода:**
```
📊 Смен пользователя 120962578 сегодня (2025/11/01): 2
Total sales за день: $1500.00

  Shift 11: $500.00 (Commission %: 10.00%)
  Shift 12: $1000.00 (Commission %: 12.00%)
```

---

## 📦 Фикстуры (fixtures/)

Тестовые данные и фикстуры для тестов (будут добавлены в будущем).

---

## 🚀 Как создать новый тест

### 1. Интеграционный тест

Создайте файл `tests/integration/test_scenario_X_Y.py`:

```python
"""
Automated Integration Test for TEST_SCENARIOS.md

Test X.Y: Description
"""

import sys
import os
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

import logging
from unittest.mock import MagicMock, AsyncMock
import asyncio

from telegram import Update, User, Message, CallbackQuery, Chat
from telegram.ext import ContextTypes, ConversationHandler

from handlers import (
    start, handle_callback_query, handle_amount_input
)
from config import Config, START, CHOOSE_DATE_IN, CHOOSE_TIME_IN, CHOOSE_TIME_OUT
from sheets_service import SheetsService

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class BotTestSimulator:
    """Simulates bot conversation for testing."""

    def __init__(self, user_id: int, username: str):
        self.user_id = user_id
        self.username = username
        self.sheets = SheetsService()

    # ... методы _create_mock_update, _create_mock_context

    async def run_test(self) -> dict:
        """Run the full test scenario."""
        # ... тестовый сценарий
        pass


async def main():
    """Run the test."""
    user_id = 120962578
    username = "StepunR"

    simulator = BotTestSimulator(user_id, username)
    results = await simulator.run_test()

    return 0 if results['success'] else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)
```

### 2. Запуск теста

```bash
python3 tests/integration/test_scenario_X_Y.py
```

---

## 🔍 Как работают интеграционные тесты

### Mock объекты

Тесты используют `unittest.mock` для имитации Telegram API:

```python
def _create_mock_update(self, callback_data: str = None):
    """Создает mock Update объект (имитирует нажатие кнопки)."""
    update = MagicMock(spec=Update)
    # ... настройка mock объекта
    return update

def _create_mock_context(self):
    """Создает mock Context объект (хранит состояние)."""
    context = MagicMock()
    context.user_data = {}
    context.bot.send_message = AsyncMock()
    return context
```

### Callback Data

Примеры callback_data для кнопок:

```python
"CREATE_SHIFT"         # Создать смену
"EDIT_SHIFT"           # Редактировать смену
"DATE_IN:0"            # Server date
"DATE_IN:-1"           # Server date - 1
"TIME:IN:09_AM"        # 9 AM (Clock in)
"TIME:OUT:05_PM"       # 5 PM (Clock out)
"PROD:Model A"         # Выбор продукта
"ADD_MODEL"            # Добавить продукт
"FINISH"               # Завершить смену
"BACK"                 # Назад
```

### Проверки (Assertions)

```python
# Проверка состояния FSM
assert result == CHOOSE_TIME_IN, f"Expected CHOOSE_TIME_IN, got {result}"

# Проверка данных в context
assert product_a in products, f"Product {product_a} not added"

# Проверка расчетов
verify("Total sales", expected_total_sales, new_shift.get('Total sales', 0))
```

---

## 📊 Метрики покрытия

### TEST_SCENARIOS.md

| Категория | Всего | Автоматизировано | Прогресс |
|-----------|-------|------------------|----------|
| Создание смены | 5 | 2 | 40% ⬜⬜⬛⬛⬛ |
| Редактирование | 3 | 0 | 0% ⬛⬛⬛⬛⬛ |
| Система рангов | 4 | 0 | 0% ⬛⬛⬛⬛⬛ |
| Бонусы | 6 | 0 | 0% ⬛⬛⬛⬛⬛ |
| Расчеты | 3 | 0 | 0% ⬛⬛⬛⬛⬛ |
| Кнопки | 2 | 0 | 0% ⬛⬛⬛⬛⬛ |
| Граничные случаи | 5 | 0 | 0% ⬛⬛⬛⬛⬛ |
| **ИТОГО** | **28** | **2** | **7%** |

---

## ⚙️ Настройка окружения для тестов

### Требования:

- Python 3.8+
- Все зависимости из `requirements.txt`
- Доступ к Google Sheets API
- Файл `.env` с настройками
- Файл `google_sheets_credentials.json`

### Переменные окружения:

Тесты используют те же переменные окружения, что и основной бот:

```env
BOT_TOKEN=your_bot_token
SPREADSHEET_ID=your_spreadsheet_id
GOOGLE_SA_JSON=google_sheets_credentials.json
```

---

## 🐛 Отладка тестов

### Включить подробные логи:

```python
logging.basicConfig(level=logging.DEBUG)
```

### Проверить Google Sheets после теста:

```bash
python3 tests/utils/check_today_shifts.py
```

### Очистить тестовые данные:

```bash
python3 tests/utils/delete_shifts.py 11 12 13
```

---

## 📝 CI/CD (будущее)

В будущем планируется добавить:

- GitHub Actions для автоматического запуска тестов
- Покрытие кода (coverage reports)
- Автоматическое тестирование при pull requests
- Интеграция с pytest

---

## 🤝 Вклад в тесты

При добавлении новых функций в бота:

1. Создайте соответствующий тест в `tests/integration/`
2. Убедитесь, что тест проходит
3. Обновите таблицу метрик в этом README
4. Добавьте описание теста в соответствующую секцию

---

**Версия:** 1.0
**Последнее обновление:** 2025-11-01
**Автор:** Claude AI
