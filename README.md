# Alex12060 Telegram Bot

Telegram bot for managing employee work shifts with PostgreSQL integration and Google Sheets sync.

## Project Structure

```
Alex12060/
├── bot.py                          # Main entry point
├── config.py                       # Configuration
├── pg_sync_worker.py               # PostgreSQL → Google Sheets sync worker
├── requirements.txt                # Python dependencies
├── .env, .env.example              # Environment variables
│
├── src/                            # Core application code
│   ├── handlers.py                 # Telegram message handlers
│   ├── keyboards.py                # Inline keyboards
│   └── time_utils.py               # Time utilities (ET timezone)
│
├── services/                       # Data services layer
│   ├── postgres_service.py         # PostgreSQL service (production)
│   ├── rank_service.py             # Rank calculation service
│   ├── cache_manager.py            # In-memory caching
│   └── singleton.py                # Singleton service instances
│
├── database/                       # Database schemas & migrations
│   ├── pg_schema.py                # PostgreSQL schema definitions
│   └── migrations/                 # Migration scripts
│
├── tests/                          # Test suite
├── scripts/                        # Utility scripts
│   └── systemd/                    # Service files
│       ├── alex12060-bot.service
│       └── alex12060-sync-worker.service
│
├── docs/                           # Documentation
└── logs/                           # Log files (gitignored)
```

## Features

- **Shift Management**: Clock in/out, edit shifts, view history
- **Sales Tracking**: Track sales by product (Model A, B, C)
- **Commission Calculation**: Base + dynamic + bonus commission system
- **Rank System**: Employee ranks based on monthly total sales
- **Bonus System**: Automatic bonus application on rank promotion
- **Admin Commands**: `/recalc_ranks` for manual rank recalculation
- **Data Sync**: PostgreSQL primary DB with Google Sheets sync

## Quick Start

### 1. Install Dependencies

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure Environment

```bash
cp .env.example .env
# Edit .env with your credentials
```

Required environment variables:
- `TELEGRAM_BOT_TOKEN` - Telegram bot token
- `DB_HOST`, `DB_NAME`, `DB_USER`, `DB_PASSWORD` - PostgreSQL credentials
- `SPREADSHEET_ID` - Google Sheets ID for sync

### 3. Run the Bot

**Development:**
```bash
python3 bot.py
```

**Production (systemd):**
```bash
sudo cp scripts/systemd/alex12060-bot.service /etc/systemd/system/
sudo systemctl enable alex12060-bot
sudo systemctl start alex12060-bot
```

## Database Schema

### Main Tables

| Table | Description |
|-------|-------------|
| `employees` | Employee info (telegram_id, hourly_wage, sales_commission) |
| `shifts` | Work shifts (clock_in/out, sales, commissions, total_made) |
| `products` | Product catalog (Model A, B, C) |
| `shift_products` | Sales per product per shift |
| `ranks` | Rank definitions with sales thresholds |
| `employee_ranks` | Monthly rank assignments |
| `active_bonuses` | Pending and applied bonuses |
| `dynamic_rates` | Dynamic commission rate tiers |
| `sync_queue` | Queue for Google Sheets sync |

### Key Calculations

```
total_per_hour = worked_hours × hourly_wage
commissions = net_sales × commission_pct / 100
total_made = total_per_hour + commissions + flat_bonuses
```

Commission breakdown:
- **Base**: Employee's `sales_commission` (default 8%)
- **Dynamic**: Based on shift sales ($0-400: 0%, $400-700: 1%, $700-1000: 2%, $1000+: 3%)
- **Bonus**: From rank promotions (percent_next, flat, etc.)

## Admin Commands

| Command | Description |
|---------|-------------|
| `/recalc_ranks` | Recalculate all employee ranks for current month |

Admin IDs are configured in `src/handlers.py`.

## Sync Architecture

```
PostgreSQL (primary) → sync_queue → pg_sync_worker.py → Google Sheets
```

The sync worker runs as a separate service and syncs:
- Shifts
- Active bonuses
- Employee ranks
- Employee settings

## Technology Stack

- **Python 3.8+**
- **python-telegram-bot** - Telegram API
- **PostgreSQL** - Primary database
- **psycopg2** - PostgreSQL driver
- **gspread** - Google Sheets API
- **systemd** - Process management

## Performance

| Backend | Latency | Scalability |
|---------|---------|-------------|
| PostgreSQL | 10-50ms | Excellent |
| With caching | <1ms | Very Good |

## Logs

- `logs/bot.log` - Main bot logs
- `logs/sync_worker.log` - Sync worker logs

## Testing

```bash
# Run all tests
python3 -m pytest tests/

# Run specific test
python3 -m pytest tests/test_postgres_service.py
```

## License

Proprietary - Alex12060 Project

---

**Version:** 3.1.0
**Last Updated:** 2025-11-29
