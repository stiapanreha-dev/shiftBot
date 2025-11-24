# Alex12060 Telegram Bot

Telegram бот для управления рабочими сменами сотрудников салона красоты с интеграцией PostgreSQL.

## 📁 Структура проекта

```
Alex12060/
├── bot.py                          # Main entry point
├── config.py                       # Configuration
├── requirements.txt                # Python dependencies
├── .env, .env.example              # Environment variables
├── .gitignore                      # Git ignore rules
│
├── src/                            # Core application code
│   ├── handlers.py                 # Telegram message handlers
│   ├── keyboards.py                # Inline keyboards
│   └── time_utils.py               # Time utilities
│
├── services/                       # Data services layer
│   ├── postgres_service.py         # PostgreSQL service (production)
│   ├── rank_service.py             # Rank calculation service
│   ├── cache_manager.py            # In-memory caching (v1.1.0)
│   └── singleton.py                # Singleton service instances
│
├── database/                       # Database schemas & migrations
│   ├── pg_schema.py                # PostgreSQL schema definitions
│   └── migrations/                 # Migration scripts
│       ├── migrate_to_postgres.py
│       ├── import_shifts_simple.py
│       ├── import_ranks_from_sheets.py
│       └── populate_ranks.py
│
├── experimental/                   # Experimental features
│   ├── sheets_service.py           # Google Sheets (legacy)
│   ├── hybrid_service.py           # Hybrid Sheets+PostgreSQL
│   ├── sync_manager.py             # Bidirectional sync
│   └── sync_worker.py              # Sync worker daemon
│
├── tests/                          # Test suite
│   ├── test_cache.py
│   ├── test_commission_breakdown.py
│   ├── test_postgres_service.py
│   ├── test_bidirectional_sync.py
│   ├── integration/                # Integration tests
│   └── utils/                      # Test utilities
│
├── scripts/                        # Utility scripts
│   ├── dev/                        # Development utilities
│   └── systemd/                    # Service files
│       ├── alex12060-bot.service
│       └── alex12060-sync-worker.service
│
├── docs/                           # Documentation
│   ├── CLAUDE.md                   # Main project guide
│   ├── README.md                   # Original README
│   ├── architecture/               # Architecture docs
│   ├── changelogs/                 # Change history
│   ├── deployment/                 # Deployment guides
│   ├── planning/                   # Planning documents
│   └── specs/                      # Specifications
│
├── archive/                        # Deprecated code
├── logs/                           # Log files (gitignored)
└── data/                           # Data files
    └── reference_data.db
```

## 🚀 Быстрый старт

### 1. Установка зависимостей

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Настройка окружения

Скопируйте `.env.example` в `.env` и заполните:

```bash
cp .env.example .env
# Отредактируйте .env с вашими данными
```

### 3. Запуск бота

**Локально (для разработки):**
```bash
python3 bot.py
```

**На сервере (production):**
```bash
# Копировать service файл
sudo cp scripts/systemd/alex12060-bot.service /etc/systemd/system/

# Включить и запустить
sudo systemctl enable alex12060-bot
sudo systemctl start alex12060-bot

# Проверить статус
sudo systemctl status alex12060-bot
```

## 📚 Документация

- **[docs/CLAUDE.md](docs/CLAUDE.md)** - Полное руководство для разработки
- **[docs/architecture/](docs/architecture/)** - Архитектурная документация
- **[docs/changelogs/](docs/changelogs/)** - История изменений
- **[docs/deployment/](docs/deployment/)** - Руководства по деплою

## 🔧 Основные функции

- ✅ Создание и редактирование смен (Clock in/out)
- ✅ Учет продаж по продуктам
- ✅ Автоматический расчет комиссии (base + dynamic + bonus)
- ✅ Система бонусов и рангов
- ✅ PostgreSQL backend (100-1500x быстрее чем Google Sheets)
- ✅ In-memory кэширование (v1.1.0)

## 🛠 Технологии

- **Python 3.8+**
- **python-telegram-bot** - Telegram API
- **PostgreSQL** - Primary database (production)
- **SQLAlchemy** - ORM
- **systemd** - Process management

## 📊 Производительность

| Backend | Latency | API Calls | Scalability |
|---------|---------|-----------|-------------|
| PostgreSQL (v3.1) | 10-50ms | 0 | ✅ Excellent |
| Caching (v1.1) | <1ms | -60% | ✅ Very Good |
| Google Sheets (legacy) | 1-3s | Many | ⚠️ Limited |

## 🔐 Безопасность

- Sensitive данные в `.env` (не в git)
- Service запускается от непривилегированного пользователя
- NoNewPrivileges и PrivateTmp в systemd

## 📝 Логи

Логи находятся в `logs/` (игнорируются git):
- `logs/bot.log` - основные логи бота
- `logs/sync_worker.log` - логи sync worker

## 🧪 Тестирование

```bash
# Запустить все тесты
./run_tests.sh

# Запустить конкретный тест
python3 -m pytest tests/test_cache.py
```

## 📞 Поддержка

При возникновении проблем см. `docs/CLAUDE.md` раздел "Устранение проблем".

## 📄 Лицензия

Proprietary - Alex12060 Project

---

**Последнее обновление:** 2025-11-24
**Версия:** 3.1.0 (PostgreSQL + Restructured)
