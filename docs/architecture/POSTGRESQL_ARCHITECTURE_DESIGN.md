# 🏗️ ПРОЕКТИРОВАНИЕ: PostgreSQL с асинхронной синхронизацией в Google Sheets

**Проект:** Alex12060 Telegram Bot - Migration to PostgreSQL
**Дата проектирования:** 2025-11-10
**Режим:** UltraThink Mode 🧠
**Статус:** DESIGN - Ready for Implementation

---

## 📋 EXECUTIVE SUMMARY

**Цель:** Мигрировать бота с Google Sheets на PostgreSQL как primary database, сохраняя Google Sheets для:
1. Визуального интерфейса для нетехнических пользователей
2. Backup и аудита
3. Ручного редактирования справочников

**Ключевые принципы:**
- ✅ PostgreSQL - **source of truth** для транзакционных данных
- ✅ Google Sheets - **read-only mirror** + ручное редактирование справочников
- ✅ Асинхронная синхронизация (не блокирует операции бота)
- ✅ Сохранение формата Google Sheets (структура, столбцы, формулы)
- ✅ Zero downtime migration
- ✅ Возможность rollback

---

## 🎯 ЧАСТЬ 1: АРХИТЕКТУРА РЕШЕНИЯ

### 1.1 High-Level Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                    TELEGRAM BOT                              │
│                                                              │
│  ┌────────────┐         ┌─────────────┐                    │
│  │ handlers.py│────────►│  db_service │                    │
│  │            │         │    .py      │                    │
│  └────────────┘         └──────┬──────┘                    │
│                                │                             │
└────────────────────────────────┼─────────────────────────────┘
                                 │
                                 ▼
        ┌────────────────────────────────────┐
        │      PostgreSQL Database           │
        │                                    │
        │  • Shifts (primary)                │
        │  • Employees                       │
        │  • Products                        │
        │  • Bonuses                         │
        │  • Dynamic Rates (cached)          │
        │  • Ranks (cached)                  │
        │  • sync_queue (для синхронизации)  │
        └────────────┬───────────────────────┘
                     │
                     │  watches changes
                     ▼
        ┌────────────────────────────────────┐
        │     Sync Worker (daemon)           │
        │                                    │
        │  • Listens to PostgreSQL events    │
        │  • Batches changes                 │
        │  • Syncs to Google Sheets          │
        │  • Handles conflicts               │
        │  • Retries on failure              │
        └────────────┬───────────────────────┘
                     │
                     │  async writes
                     ▼
        ┌────────────────────────────────────┐
        │      Google Sheets (Mirror)        │
        │                                    │
        │  • Shifts (read-only mirror)       │
        │  • EmployeeSettings (editable)     │
        │  • DynamicRates (editable)         │
        │  • Ranks (editable)                │
        │  • ActiveBonuses (read-only)       │
        └────────────────────────────────────┘
```

### 1.2 Data Flow

**Создание смены:**
```
1. User → Telegram Bot
2. Bot → handlers.py → db_service.create_shift()
3. db_service → PostgreSQL INSERT (0.05s)
4. PostgreSQL → Trigger → sync_queue.INSERT
5. Bot → User (instant response! ✅)
6. [Async] Sync Worker → sync_queue → Google Sheets (background)
```

**Редактирование справочников:**
```
1. Admin → Google Sheets (edit DynamicRates)
2. [Periodic] Sync Worker → Poll Google Sheets
3. Sync Worker → PostgreSQL UPDATE
4. PostgreSQL → Cache invalidation
```

### 1.3 Компоненты системы

**1. PostgreSQL Database**
- Primary data store
- ACID транзакции
- Индексы для быстрого поиска
- Triggers для tracking изменений

**2. db_service.py**
- Новый сервис для работы с PostgreSQL
- ORM (SQLAlchemy)
- Connection pooling
- Query optimization

**3. Sync Worker (sheets_sync_worker.py)**
- Daemon процесс (systemd service)
- Читает sync_queue
- Batching для эффективности
- Retry logic с exponential backoff
- Conflict resolution

**4. Migration Service**
- Одноразовая миграция Google Sheets → PostgreSQL
- Валидация данных
- Сохранение ID mapping

**5. Monitoring & Logging**
- Prometheus metrics
- Grafana dashboards
- Structured logging

---

## 🗄️ ЧАСТЬ 2: СХЕМА БАЗЫ ДАННЫХ

### 2.1 PostgreSQL Schema (полная)

```sql
-- ============================================================
-- CORE TABLES (транзакционные данные)
-- ============================================================

-- Employees table
CREATE TABLE employees (
    id INTEGER PRIMARY KEY,  -- Telegram User ID
    name VARCHAR(100) NOT NULL,
    hourly_wage NUMERIC(10,2) DEFAULT 15.00,
    base_commission NUMERIC(5,2) DEFAULT 8.00,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_employees_name ON employees(name);

-- Shifts table (главная таблица)
CREATE TABLE shifts (
    id SERIAL PRIMARY KEY,
    date TIMESTAMP NOT NULL,
    employee_id INTEGER NOT NULL REFERENCES employees(id),
    employee_name VARCHAR(100) NOT NULL,  -- denormalized для быстроты
    clock_in TIMESTAMP NOT NULL,
    clock_out TIMESTAMP NOT NULL,
    worked_hours NUMERIC(5,2) NOT NULL,
    total_sales NUMERIC(10,2) NOT NULL,
    net_sales NUMERIC(10,2) NOT NULL,
    commission_pct NUMERIC(5,2) NOT NULL,
    total_per_hour NUMERIC(10,2) NOT NULL,
    commissions NUMERIC(10,2) NOT NULL,
    total_made NUMERIC(10,2) NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    synced_to_sheets BOOLEAN DEFAULT FALSE,
    sheets_sync_at TIMESTAMP NULL,

    CONSTRAINT valid_times CHECK (clock_out > clock_in),
    CONSTRAINT positive_hours CHECK (worked_hours > 0),
    CONSTRAINT positive_sales CHECK (total_sales >= 0)
);

-- Indexes для производительности
CREATE INDEX idx_shifts_employee_date ON shifts(employee_id, date DESC);
CREATE INDEX idx_shifts_date ON shifts(date DESC);
CREATE INDEX idx_shifts_created_at ON shifts(created_at DESC);
CREATE INDEX idx_shifts_sync_pending ON shifts(synced_to_sheets) WHERE synced_to_sheets = FALSE;

-- Products table (нормализованная структура)
CREATE TABLE products (
    id SERIAL PRIMARY KEY,
    name VARCHAR(50) NOT NULL UNIQUE,
    display_order INTEGER NOT NULL DEFAULT 0,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Вставляем продукты
INSERT INTO products (name, display_order) VALUES
    ('Bella', 1),
    ('Laura', 2),
    ('Sophie', 3),
    ('Alice', 4),
    ('Emma', 5),
    ('Molly', 6),
    ('Other', 7);

-- Shift products (связь смен с продуктами)
CREATE TABLE shift_products (
    id SERIAL PRIMARY KEY,
    shift_id INTEGER NOT NULL REFERENCES shifts(id) ON DELETE CASCADE,
    product_id INTEGER NOT NULL REFERENCES products(id),
    amount NUMERIC(10,2) NOT NULL CHECK (amount >= 0),

    CONSTRAINT unique_shift_product UNIQUE(shift_id, product_id)
);

CREATE INDEX idx_shift_products_shift ON shift_products(shift_id);
CREATE INDEX idx_shift_products_product ON shift_products(product_id);

-- ============================================================
-- REFERENCE DATA (справочники - кэшируются)
-- ============================================================

-- Dynamic rates table
CREATE TABLE dynamic_rates (
    id SERIAL PRIMARY KEY,
    min_amount NUMERIC(10,2) NOT NULL,
    max_amount NUMERIC(10,2) NOT NULL,
    percentage NUMERIC(5,2) NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),

    CONSTRAINT valid_range CHECK (max_amount > min_amount),
    CONSTRAINT valid_percentage CHECK (percentage >= 0 AND percentage <= 100)
);

CREATE INDEX idx_dynamic_rates_range ON dynamic_rates(min_amount, max_amount) WHERE is_active = TRUE;

-- Ranks table
CREATE TABLE ranks (
    id SERIAL PRIMARY KEY,
    name VARCHAR(50) NOT NULL UNIQUE,
    min_amount NUMERIC(10,2) NOT NULL,
    max_amount NUMERIC(10,2) NOT NULL,
    text TEXT,
    display_order INTEGER NOT NULL DEFAULT 0,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),

    CONSTRAINT valid_rank_range CHECK (max_amount > min_amount)
);

CREATE INDEX idx_ranks_range ON ranks(min_amount, max_amount) WHERE is_active = TRUE;

-- Rank bonuses table (связь rank → bonuses)
CREATE TABLE rank_bonuses (
    id SERIAL PRIMARY KEY,
    rank_id INTEGER NOT NULL REFERENCES ranks(id) ON DELETE CASCADE,
    bonus_code VARCHAR(50) NOT NULL,
    position INTEGER NOT NULL,

    CONSTRAINT unique_rank_position UNIQUE(rank_id, position)
);

CREATE INDEX idx_rank_bonuses_rank ON rank_bonuses(rank_id);

-- ============================================================
-- BONUSES SYSTEM
-- ============================================================

-- Active bonuses table
CREATE TABLE active_bonuses (
    id SERIAL PRIMARY KEY,
    employee_id INTEGER NOT NULL REFERENCES employees(id),
    bonus_type VARCHAR(50) NOT NULL,
    value NUMERIC(10,2) NOT NULL,
    applied BOOLEAN DEFAULT FALSE,
    shift_id INTEGER NULL REFERENCES shifts(id) ON DELETE SET NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    applied_at TIMESTAMP NULL,
    synced_to_sheets BOOLEAN DEFAULT FALSE,

    CONSTRAINT valid_bonus_type CHECK (bonus_type IN (
        'percent_next', 'percent_all', 'percent_prev',
        'double_commission', 'flat', 'flat_immediate'
    ))
);

CREATE INDEX idx_active_bonuses_employee ON active_bonuses(employee_id, applied) WHERE applied = FALSE;
CREATE INDEX idx_active_bonuses_shift ON active_bonuses(shift_id);
CREATE INDEX idx_active_bonuses_sync_pending ON active_bonuses(synced_to_sheets) WHERE synced_to_sheets = FALSE;

-- Employee ranks table
CREATE TABLE employee_ranks (
    id SERIAL PRIMARY KEY,
    employee_id INTEGER NOT NULL REFERENCES employees(id),
    current_rank_id INTEGER NOT NULL REFERENCES ranks(id),
    previous_rank_id INTEGER NULL REFERENCES ranks(id),
    month INTEGER NOT NULL CHECK (month BETWEEN 1 AND 12),
    year INTEGER NOT NULL CHECK (year >= 2000),
    total_sales NUMERIC(10,2) DEFAULT 0,
    notified BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    synced_to_sheets BOOLEAN DEFAULT FALSE,

    CONSTRAINT unique_employee_month UNIQUE(employee_id, year, month)
);

CREATE INDEX idx_employee_ranks_employee ON employee_ranks(employee_id);
CREATE INDEX idx_employee_ranks_period ON employee_ranks(year, month);
CREATE INDEX idx_employee_ranks_sync_pending ON employee_ranks(synced_to_sheets) WHERE synced_to_sheets = FALSE;

-- ============================================================
-- SYNC INFRASTRUCTURE
-- ============================================================

-- Sync queue table (для tracking изменений)
CREATE TABLE sync_queue (
    id SERIAL PRIMARY KEY,
    table_name VARCHAR(50) NOT NULL,
    record_id INTEGER NOT NULL,
    operation VARCHAR(10) NOT NULL,  -- INSERT, UPDATE, DELETE
    data JSONB NOT NULL,
    priority INTEGER DEFAULT 5,  -- 1=highest, 10=lowest
    status VARCHAR(20) DEFAULT 'pending',  -- pending, processing, completed, failed
    attempts INTEGER DEFAULT 0,
    max_attempts INTEGER DEFAULT 5,
    error_message TEXT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    processed_at TIMESTAMP NULL,

    CONSTRAINT valid_operation CHECK (operation IN ('INSERT', 'UPDATE', 'DELETE')),
    CONSTRAINT valid_status CHECK (status IN ('pending', 'processing', 'completed', 'failed'))
);

CREATE INDEX idx_sync_queue_status ON sync_queue(status, priority, created_at) WHERE status = 'pending';
CREATE INDEX idx_sync_queue_table_record ON sync_queue(table_name, record_id);

-- Sync log table (аудит синхронизации)
CREATE TABLE sync_log (
    id SERIAL PRIMARY KEY,
    sync_queue_id INTEGER REFERENCES sync_queue(id) ON DELETE SET NULL,
    table_name VARCHAR(50) NOT NULL,
    record_id INTEGER NOT NULL,
    operation VARCHAR(10) NOT NULL,
    status VARCHAR(20) NOT NULL,
    duration_ms INTEGER,
    error_message TEXT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_sync_log_created_at ON sync_log(created_at DESC);
CREATE INDEX idx_sync_log_status ON sync_log(status);

-- ============================================================
-- MATERIALIZED VIEWS (для аналитики и производительности)
-- ============================================================

-- Daily sales by employee (для быстрого расчета динамической ставки)
CREATE MATERIALIZED VIEW employee_daily_sales AS
SELECT
    employee_id,
    DATE(date) as sale_date,
    SUM(total_sales) as total_sales,
    SUM(net_sales) as net_sales,
    COUNT(*) as shift_count,
    SUM(worked_hours) as total_hours,
    AVG(commission_pct) as avg_commission_pct
FROM shifts
GROUP BY employee_id, DATE(date);

CREATE UNIQUE INDEX idx_emp_daily_sales_unique ON employee_daily_sales(employee_id, sale_date);
CREATE INDEX idx_emp_daily_sales_date ON employee_daily_sales(sale_date DESC);

-- Refresh function
CREATE OR REPLACE FUNCTION refresh_employee_daily_sales()
RETURNS TRIGGER AS $$
BEGIN
    REFRESH MATERIALIZED VIEW CONCURRENTLY employee_daily_sales;
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

-- Trigger to refresh materialized view
CREATE TRIGGER trigger_refresh_daily_sales
AFTER INSERT OR UPDATE OR DELETE ON shifts
FOR EACH STATEMENT
EXECUTE FUNCTION refresh_employee_daily_sales();

-- Monthly sales by employee (для рангов)
CREATE MATERIALIZED VIEW employee_monthly_sales AS
SELECT
    employee_id,
    EXTRACT(YEAR FROM date)::INTEGER as year,
    EXTRACT(MONTH FROM date)::INTEGER as month,
    SUM(total_sales) as total_sales,
    SUM(net_sales) as net_sales,
    COUNT(*) as shift_count,
    SUM(worked_hours) as total_hours,
    SUM(total_made) as total_earned
FROM shifts
GROUP BY employee_id, EXTRACT(YEAR FROM date), EXTRACT(MONTH FROM date);

CREATE UNIQUE INDEX idx_emp_monthly_sales_unique ON employee_monthly_sales(employee_id, year, month);
CREATE INDEX idx_emp_monthly_sales_period ON employee_monthly_sales(year, month);

-- ============================================================
-- TRIGGERS для автоматической синхронизации
-- ============================================================

-- Function to add to sync queue
CREATE OR REPLACE FUNCTION add_to_sync_queue()
RETURNS TRIGGER AS $$
BEGIN
    -- Determine operation
    DECLARE
        op VARCHAR(10);
        rec_data JSONB;
        rec_id INTEGER;
    BEGIN
        IF TG_OP = 'DELETE' THEN
            op := 'DELETE';
            rec_data := row_to_json(OLD)::JSONB;
            rec_id := OLD.id;
        ELSIF TG_OP = 'UPDATE' THEN
            op := 'UPDATE';
            rec_data := row_to_json(NEW)::JSONB;
            rec_id := NEW.id;
        ELSIF TG_OP = 'INSERT' THEN
            op := 'INSERT';
            rec_data := row_to_json(NEW)::JSONB;
            rec_id := NEW.id;
        END IF;

        -- Insert into sync queue
        INSERT INTO sync_queue (table_name, record_id, operation, data)
        VALUES (TG_TABLE_NAME, rec_id, op, rec_data);

        RETURN NEW;
    END;
END;
$$ LANGUAGE plpgsql;

-- Triggers для основных таблиц
CREATE TRIGGER trigger_sync_shifts
AFTER INSERT OR UPDATE OR DELETE ON shifts
FOR EACH ROW
EXECUTE FUNCTION add_to_sync_queue();

CREATE TRIGGER trigger_sync_active_bonuses
AFTER INSERT OR UPDATE OR DELETE ON active_bonuses
FOR EACH ROW
EXECUTE FUNCTION add_to_sync_queue();

CREATE TRIGGER trigger_sync_employee_ranks
AFTER INSERT OR UPDATE OR DELETE ON employee_ranks
FOR EACH ROW
EXECUTE FUNCTION add_to_sync_queue();

-- ============================================================
-- HELPER FUNCTIONS
-- ============================================================

-- Get dynamic rate for amount
CREATE OR REPLACE FUNCTION get_dynamic_rate(sales_amount NUMERIC)
RETURNS NUMERIC AS $$
DECLARE
    rate NUMERIC;
BEGIN
    SELECT percentage INTO rate
    FROM dynamic_rates
    WHERE is_active = TRUE
      AND min_amount <= sales_amount
      AND max_amount > sales_amount
    LIMIT 1;

    RETURN COALESCE(rate, 0);
END;
$$ LANGUAGE plpgsql;

-- Get employee rank for month
CREATE OR REPLACE FUNCTION get_employee_rank(emp_id INTEGER, year_val INTEGER, month_val INTEGER)
RETURNS VARCHAR AS $$
DECLARE
    monthly_sales NUMERIC;
    rank_name VARCHAR;
BEGIN
    -- Get total sales for month
    SELECT total_sales INTO monthly_sales
    FROM employee_monthly_sales
    WHERE employee_id = emp_id
      AND year = year_val
      AND month = month_val;

    -- Find matching rank
    SELECT name INTO rank_name
    FROM ranks
    WHERE is_active = TRUE
      AND min_amount <= COALESCE(monthly_sales, 0)
      AND max_amount > COALESCE(monthly_sales, 0)
    LIMIT 1;

    RETURN COALESCE(rank_name, 'Rookie');
END;
$$ LANGUAGE plpgsql;

-- ============================================================
-- INDEXES для поиска и производительности
-- ============================================================

-- Additional composite indexes
CREATE INDEX idx_shifts_lookup ON shifts(employee_id, date, id);
CREATE INDEX idx_shifts_date_employee ON shifts(date, employee_id) WHERE synced_to_sheets = TRUE;

-- ============================================================
-- CONSTRAINTS и POLICIES
-- ============================================================

-- Row level security (опционально, для будущего multi-tenancy)
ALTER TABLE shifts ENABLE ROW LEVEL SECURITY;
ALTER TABLE active_bonuses ENABLE ROW LEVEL SECURITY;

-- Default policies (allow all for now, можно ужесточить позже)
CREATE POLICY shifts_policy ON shifts FOR ALL USING (true);
CREATE POLICY bonuses_policy ON active_bonuses FOR ALL USING (true);
```

### 2.2 Google Sheets Structure (сохраняется текущая)

**Таблицы в Google Sheets:**

1. **Shifts** (read-only mirror)
   - Все столбцы как сейчас
   - Формулы сохраняются
   - Синхронизация из PostgreSQL

2. **EmployeeSettings** (editable)
   - EmployeeId, Hourly wage, Sales commission
   - Периодически читается в PostgreSQL

3. **DynamicRates** (editable)
   - Min Amount, Max Amount, Percentage
   - Периодически читается в PostgreSQL

4. **Ranks** (editable)
   - Rank Name, Min/Max Amount, Bonuses, TEXT
   - Периодически читается в PostgreSQL

5. **ActiveBonuses** (read-only mirror)
   - Синхронизация из PostgreSQL

6. **EmployeeRanks** (read-only mirror)
   - Синхронизация из PostgreSQL

---

## 🔄 ЧАСТЬ 3: МЕХАНИЗМ СИНХРОНИЗАЦИИ

### 3.1 Sync Worker Architecture

```python
# File: sheets_sync_worker.py

import asyncio
import logging
from typing import List, Dict, Optional
from datetime import datetime, timedelta
import signal
import sys

import psycopg2
from psycopg2.extras import RealDictCursor
import gspread

logger = logging.getLogger(__name__)

class SheetsSyncWorker:
    """Background worker for syncing PostgreSQL → Google Sheets."""

    def __init__(self):
        self.running = True
        self.db_conn = None
        self.sheets_client = None
        self.spreadsheet = None

        # Configuration
        self.batch_size = 10
        self.sync_interval = 5  # seconds
        self.max_retry_attempts = 5
        self.retry_delay_base = 2  # seconds

        # Statistics
        self.stats = {
            'total_synced': 0,
            'total_failed': 0,
            'last_sync_at': None,
        }

    def setup(self):
        """Setup connections and signal handlers."""
        # Database connection
        self.db_conn = psycopg2.connect(
            host='localhost',
            database='alex12060',
            user='alex12060_user',
            password='...',
            cursor_factory=RealDictCursor
        )

        # Google Sheets connection
        self.sheets_client = gspread.service_account(
            filename='google_sheets_credentials.json'
        )
        self.spreadsheet = self.sheets_client.open_by_key(SPREADSHEET_ID)

        # Signal handlers for graceful shutdown
        signal.signal(signal.SIGTERM, self.handle_shutdown)
        signal.signal(signal.SIGINT, self.handle_shutdown)

        logger.info("Sync worker setup completed")

    def handle_shutdown(self, signum, frame):
        """Handle graceful shutdown."""
        logger.info(f"Received signal {signum}, shutting down gracefully...")
        self.running = False

    async def run(self):
        """Main worker loop."""
        logger.info("Sync worker started")

        while self.running:
            try:
                # Get pending items from sync queue
                items = self.get_pending_sync_items()

                if items:
                    logger.info(f"Processing {len(items)} sync items")
                    await self.process_sync_batch(items)

                # Update statistics
                self.stats['last_sync_at'] = datetime.now()

                # Sleep before next iteration
                await asyncio.sleep(self.sync_interval)

            except Exception as e:
                logger.error(f"Error in sync worker loop: {e}", exc_info=True)
                await asyncio.sleep(self.sync_interval * 2)

        logger.info("Sync worker stopped")

    def get_pending_sync_items(self) -> List[Dict]:
        """Get pending items from sync_queue."""
        with self.db_conn.cursor() as cursor:
            cursor.execute("""
                SELECT * FROM sync_queue
                WHERE status = 'pending'
                  AND attempts < max_attempts
                ORDER BY priority ASC, created_at ASC
                LIMIT %s
            """, (self.batch_size,))

            return cursor.fetchall()

    async def process_sync_batch(self, items: List[Dict]):
        """Process batch of sync items."""
        for item in items:
            try:
                # Mark as processing
                self.update_sync_status(item['id'], 'processing')

                # Sync to Google Sheets
                success = await self.sync_to_sheets(item)

                if success:
                    self.update_sync_status(item['id'], 'completed')
                    self.log_sync_success(item)
                    self.stats['total_synced'] += 1
                else:
                    self.handle_sync_failure(item)

            except Exception as e:
                logger.error(f"Error processing sync item {item['id']}: {e}")
                self.handle_sync_failure(item, str(e))

    async def sync_to_sheets(self, item: Dict) -> bool:
        """Sync single item to Google Sheets.

        Returns:
            True if successful, False otherwise.
        """
        table_name = item['table_name']
        operation = item['operation']
        data = item['data']

        try:
            if table_name == 'shifts':
                return await self.sync_shift(operation, data)
            elif table_name == 'active_bonuses':
                return await self.sync_bonus(operation, data)
            elif table_name == 'employee_ranks':
                return await self.sync_employee_rank(operation, data)
            else:
                logger.warning(f"Unknown table for sync: {table_name}")
                return False

        except gspread.exceptions.APIError as e:
            if e.response.status_code == 429:
                # Rate limit - wait and retry
                logger.warning("Rate limit hit, waiting...")
                await asyncio.sleep(60)
                return False
            raise

    async def sync_shift(self, operation: str, shift_data: Dict) -> bool:
        """Sync shift to Google Sheets Shifts table."""
        ws = self.spreadsheet.worksheet('Shifts')

        # Get products for this shift
        products = self.get_shift_products(shift_data['id'])

        # Build row in Google Sheets format
        row = self.build_shift_row(shift_data, products)

        if operation == 'INSERT':
            # Find next empty row or append
            ws.append_row(row, value_input_option='RAW')
            logger.info(f"Inserted shift {shift_data['id']} to Sheets")

        elif operation == 'UPDATE':
            # Find row by ID
            row_idx = self.find_sheets_row_by_id(ws, shift_data['id'])
            if row_idx:
                # Update row
                ws.update(f'A{row_idx}:Z{row_idx}', [row], value_input_option='RAW')
                logger.info(f"Updated shift {shift_data['id']} in Sheets")
            else:
                logger.warning(f"Shift {shift_data['id']} not found in Sheets for update")
                return False

        elif operation == 'DELETE':
            # Find and delete row
            row_idx = self.find_sheets_row_by_id(ws, shift_data['id'])
            if row_idx:
                ws.delete_rows(row_idx)
                logger.info(f"Deleted shift {shift_data['id']} from Sheets")
            else:
                logger.warning(f"Shift {shift_data['id']} not found in Sheets for deletion")

        # Mark as synced in PostgreSQL
        self.mark_shift_synced(shift_data['id'])

        return True

    def build_shift_row(self, shift_data: Dict, products: Dict) -> List:
        """Build row for Shifts worksheet in correct order."""
        # Get headers from worksheet
        ws = self.spreadsheet.worksheet('Shifts')
        headers = ws.row_values(1)

        # Build row dict
        row_dict = {
            'ID': shift_data['id'],
            'Date': shift_data['date'].strftime('%Y/%m/%d'),
            'EmployeeId': shift_data['employee_id'],
            'EmployeeName': shift_data['employee_name'],
            'Clock in': shift_data['clock_in'].strftime('%Y/%m/%d %H:%M:%S'),
            'Clock out': shift_data['clock_out'].strftime('%Y/%m/%d %H:%M:%S'),
            'Worked hours/shift': f"{shift_data['worked_hours']:.2f}",
            'Total sales': f"{shift_data['total_sales']:.2f}",
            'Net sales': f"{shift_data['net_sales']:.2f}",
            '%': f"{shift_data['commission_pct']:.2f}",
            'Total per hour': f"{shift_data['total_per_hour']:.2f}",
            'Commissions': f"{shift_data['commissions']:.2f}",
            'Total made': f"{shift_data['total_made']:.2f}",
        }

        # Add products
        for product_name, amount in products.items():
            row_dict[product_name] = f"{amount:.2f}"

        # Build row in order of headers
        row = [row_dict.get(h, '') for h in headers]

        return row

    def get_shift_products(self, shift_id: int) -> Dict[str, float]:
        """Get products for shift from PostgreSQL."""
        with self.db_conn.cursor() as cursor:
            cursor.execute("""
                SELECT p.name, sp.amount
                FROM shift_products sp
                JOIN products p ON p.id = sp.product_id
                WHERE sp.shift_id = %s
            """, (shift_id,))

            return {row['name']: float(row['amount']) for row in cursor.fetchall()}

    def find_sheets_row_by_id(self, ws, record_id: int) -> Optional[int]:
        """Find row number in Google Sheets by ID."""
        ids = ws.col_values(1)[1:]  # Skip header

        for idx, id_str in enumerate(ids, start=2):
            try:
                if int(id_str.strip()) == record_id:
                    return idx
            except (ValueError, AttributeError):
                continue

        return None

    def mark_shift_synced(self, shift_id: int):
        """Mark shift as synced in PostgreSQL."""
        with self.db_conn.cursor() as cursor:
            cursor.execute("""
                UPDATE shifts
                SET synced_to_sheets = TRUE,
                    sheets_sync_at = NOW()
                WHERE id = %s
            """, (shift_id,))
            self.db_conn.commit()

    def update_sync_status(self, queue_id: int, status: str):
        """Update sync queue item status."""
        with self.db_conn.cursor() as cursor:
            cursor.execute("""
                UPDATE sync_queue
                SET status = %s,
                    processed_at = NOW()
                WHERE id = %s
            """, (status, queue_id))
            self.db_conn.commit()

    def handle_sync_failure(self, item: Dict, error_msg: str = None):
        """Handle sync failure with retry logic."""
        attempts = item['attempts'] + 1

        if attempts >= item['max_attempts']:
            status = 'failed'
            logger.error(f"Sync item {item['id']} failed permanently after {attempts} attempts")
            self.stats['total_failed'] += 1
        else:
            status = 'pending'
            logger.warning(f"Sync item {item['id']} failed, will retry (attempt {attempts})")

        with self.db_conn.cursor() as cursor:
            cursor.execute("""
                UPDATE sync_queue
                SET status = %s,
                    attempts = %s,
                    error_message = %s
                WHERE id = %s
            """, (status, attempts, error_msg, item['id']))
            self.db_conn.commit()

    def log_sync_success(self, item: Dict):
        """Log successful sync."""
        with self.db_conn.cursor() as cursor:
            cursor.execute("""
                INSERT INTO sync_log (
                    sync_queue_id, table_name, record_id,
                    operation, status, created_at
                )
                VALUES (%s, %s, %s, %s, %s, NOW())
            """, (
                item['id'],
                item['table_name'],
                item['record_id'],
                item['operation'],
                'completed'
            ))
            self.db_conn.commit()

    async def periodic_reference_data_sync(self):
        """Периодическая синхронизация справочников Sheets → PostgreSQL."""
        while self.running:
            try:
                logger.info("Syncing reference data from Sheets to PostgreSQL")

                # Sync EmployeeSettings
                await self.sync_employee_settings_from_sheets()

                # Sync DynamicRates
                await self.sync_dynamic_rates_from_sheets()

                # Sync Ranks
                await self.sync_ranks_from_sheets()

                logger.info("Reference data sync completed")

            except Exception as e:
                logger.error(f"Error syncing reference data: {e}", exc_info=True)

            # Wait 5 minutes before next sync
            await asyncio.sleep(300)

    async def sync_employee_settings_from_sheets(self):
        """Sync EmployeeSettings from Sheets to PostgreSQL."""
        ws = self.spreadsheet.worksheet('EmployeeSettings')
        records = ws.get_all_records()

        with self.db_conn.cursor() as cursor:
            for record in records:
                cursor.execute("""
                    INSERT INTO employees (id, hourly_wage, base_commission)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (id) DO UPDATE SET
                        hourly_wage = EXCLUDED.hourly_wage,
                        base_commission = EXCLUDED.base_commission,
                        updated_at = NOW()
                """, (
                    record['EmployeeId'],
                    record['Hourly wage'],
                    record['Sales commission']
                ))

            self.db_conn.commit()

        logger.info(f"Synced {len(records)} employee settings")

    # Similar methods for DynamicRates, Ranks...
```

### 3.2 Systemd Service для Sync Worker

```ini
# File: /etc/systemd/system/alex12060-sync-worker.service

[Unit]
Description=Alex12060 Sheets Sync Worker
After=network.target postgresql.service
Requires=postgresql.service

[Service]
Type=simple
User=lexun
WorkingDirectory=/home/lexun/Alex12060
ExecStart=/home/lexun/Alex12060/venv/bin/python3 /home/lexun/Alex12060/sheets_sync_worker.py
Restart=always
RestartSec=10
StandardOutput=append:/home/lexun/Alex12060/sync_worker.log
StandardError=append:/home/lexun/Alex12060/sync_worker.log

# Resource limits
MemoryLimit=512M
CPUQuota=50%

[Install]
WantedBy=multi-user.target
```

---

## 🔀 ЧАСТЬ 4: МИГРАЦИЯ ДАННЫХ

### 4.1 Migration Script

```python
# File: migrate_sheets_to_postgres.py

"""One-time migration script from Google Sheets to PostgreSQL."""

import logging
from typing import Dict, List
from datetime import datetime

import gspread
import psycopg2
from psycopg2.extras import execute_batch

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class SheetsMigration:
    """Handles migration from Google Sheets to PostgreSQL."""

    def __init__(self):
        # Setup connections
        self.sheets_client = gspread.service_account(
            filename='google_sheets_credentials.json'
        )
        self.spreadsheet = self.sheets_client.open_by_key(SPREADSHEET_ID)

        self.db_conn = psycopg2.connect(
            host='localhost',
            database='alex12060',
            user='alex12060_user',
            password='...'
        )

        # ID mapping (Sheets ID → PostgreSQL ID)
        self.id_mapping = {
            'shifts': {},
            'bonuses': {},
            'ranks': {}
        }

    def run_migration(self):
        """Run full migration."""
        logger.info("Starting migration from Google Sheets to PostgreSQL")

        try:
            # Step 1: Migrate reference data
            self.migrate_employee_settings()
            self.migrate_dynamic_rates()
            self.migrate_ranks()

            # Step 2: Migrate transactional data
            self.migrate_shifts()
            self.migrate_active_bonuses()
            self.migrate_employee_ranks()

            # Step 3: Verify migration
            self.verify_migration()

            logger.info("Migration completed successfully!")

        except Exception as e:
            logger.error(f"Migration failed: {e}", exc_info=True)
            self.db_conn.rollback()
            raise

    def migrate_shifts(self):
        """Migrate Shifts table."""
        ws = self.spreadsheet.worksheet('Shifts')
        records = ws.get_all_records()

        logger.info(f"Migrating {len(records)} shifts...")

        shifts_data = []
        products_data = []

        for record in records:
            # Parse shift data
            shift = {
                'sheets_id': record['ID'],
                'date': datetime.strptime(record['Date'], '%Y/%m/%d'),
                'employee_id': record['EmployeeId'],
                'employee_name': record['EmployeeName'],
                'clock_in': datetime.strptime(record['Clock in'], '%Y/%m/%d %H:%M:%S'),
                'clock_out': datetime.strptime(record['Clock out'], '%Y/%m/%d %H:%M:%S'),
                'worked_hours': float(record['Worked hours/shift']),
                'total_sales': float(record['Total sales']),
                'net_sales': float(record['Net sales']),
                'commission_pct': float(record['%']),
                'total_per_hour': float(record['Total per hour']),
                'commissions': float(record['Commissions']),
                'total_made': float(record['Total made']),
                'synced_to_sheets': True
            }

            shifts_data.append(shift)

            # Extract products
            for product in ['Bella', 'Laura', 'Sophie', 'Alice', 'Emma', 'Molly', 'Other']:
                amount = record.get(product, 0)
                if amount and float(amount) > 0:
                    products_data.append({
                        'sheets_shift_id': record['ID'],
                        'product_name': product,
                        'amount': float(amount)
                    })

        # Batch insert shifts
        with self.db_conn.cursor() as cursor:
            # Insert shifts
            execute_batch(cursor, """
                INSERT INTO shifts (
                    date, employee_id, employee_name, clock_in, clock_out,
                    worked_hours, total_sales, net_sales, commission_pct,
                    total_per_hour, commissions, total_made, synced_to_sheets
                )
                VALUES (
                    %(date)s, %(employee_id)s, %(employee_name)s,
                    %(clock_in)s, %(clock_out)s, %(worked_hours)s,
                    %(total_sales)s, %(net_sales)s, %(commission_pct)s,
                    %(total_per_hour)s, %(commissions)s, %(total_made)s,
                    %(synced_to_sheets)s
                )
                RETURNING id
            """, shifts_data)

            # Get generated IDs
            new_ids = cursor.fetchall()
            for idx, (new_id,) in enumerate(new_ids):
                sheets_id = shifts_data[idx]['sheets_id']
                self.id_mapping['shifts'][sheets_id] = new_id

            # Insert products
            for product in products_data:
                shift_id = self.id_mapping['shifts'][product['sheets_shift_id']]

                cursor.execute("""
                    INSERT INTO shift_products (shift_id, product_id, amount)
                    SELECT %s, id, %s FROM products WHERE name = %s
                """, (shift_id, product['amount'], product['product_name']))

            self.db_conn.commit()

        logger.info(f"Migrated {len(shifts_data)} shifts with {len(products_data)} products")

    def verify_migration(self):
        """Verify migration was successful."""
        logger.info("Verifying migration...")

        with self.db_conn.cursor() as cursor:
            # Count records
            cursor.execute("SELECT COUNT(*) FROM shifts")
            shifts_count = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM shift_products")
            products_count = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM active_bonuses")
            bonuses_count = cursor.fetchone()[0]

            logger.info(f"PostgreSQL counts:")
            logger.info(f"  Shifts: {shifts_count}")
            logger.info(f"  Products: {products_count}")
            logger.info(f"  Bonuses: {bonuses_count}")

        # Compare with Google Sheets
        ws_shifts = self.spreadsheet.worksheet('Shifts')
        sheets_shifts_count = len(ws_shifts.get_all_records())

        if shifts_count == sheets_shifts_count:
            logger.info("✅ Shift counts match!")
        else:
            logger.warning(f"⚠️ Shift counts don't match: PG={shifts_count}, Sheets={sheets_shifts_count}")

if __name__ == '__main__':
    migration = SheetsMigration()
    migration.run_migration()
```

---

## 📊 ЧАСТЬ 5: МОНИТОРИНГ И АНАЛИТИКА

### 5.1 Prometheus Metrics

```python
# File: metrics.py

from prometheus_client import Counter, Histogram, Gauge, start_http_server

# Database metrics
db_query_duration = Histogram(
    'db_query_duration_seconds',
    'Database query duration',
    ['operation', 'table']
)

db_connections = Gauge(
    'db_connections_active',
    'Active database connections'
)

# Sync metrics
sync_items_processed = Counter(
    'sync_items_processed_total',
    'Total sync items processed',
    ['status']
)

sync_duration = Histogram(
    'sync_duration_seconds',
    'Sync operation duration',
    ['table', 'operation']
)

sync_queue_size = Gauge(
    'sync_queue_size',
    'Number of items in sync queue',
    ['status']
)

# Bot metrics
bot_operations = Counter(
    'bot_operations_total',
    'Total bot operations',
    ['operation', 'status']
)

bot_response_time = Histogram(
    'bot_response_time_seconds',
    'Bot operation response time',
    ['operation']
)

# Start metrics server
start_http_server(9090)
```

### 5.2 Grafana Dashboard (JSON config)

```json
{
  "dashboard": {
    "title": "Alex12060 Bot Metrics",
    "panels": [
      {
        "title": "Sync Queue Size",
        "targets": [
          {
            "expr": "sync_queue_size{status=\"pending\"}"
          }
        ]
      },
      {
        "title": "Bot Response Time (p95)",
        "targets": [
          {
            "expr": "histogram_quantile(0.95, rate(bot_response_time_seconds_bucket[5m]))"
          }
        ]
      },
      {
        "title": "DB Query Duration (p99)",
        "targets": [
          {
            "expr": "histogram_quantile(0.99, rate(db_query_duration_seconds_bucket[5m]))"
          }
        ]
      }
    ]
  }
}
```

---

## ⚠️ ЧАСТЬ 6: ОБРАБОТКА EDGE CASES

### 6.1 Conflict Resolution

**Сценарий 1: Конфликт редактирования справочника**
```
1. Admin редактирует DynamicRates в Google Sheets
2. Sync worker читает изменения
3. Обновляет PostgreSQL
4. Инвалидирует кэш
5. Бот использует новые значения
```

**Сценарий 2: Sync worker offline**
```
1. Бот продолжает работать с PostgreSQL
2. Данные накапливаются в sync_queue
3. Когда worker вернется online - sync backlog
4. Batch processing для быстрой синхронизации
```

**Сценарий 3: Google Sheets unavailable**
```
1. Sync worker ловит exception
2. Записывает в failed status
3. Retry с exponential backoff
4. Alert в мониторинг
5. Бот продолжает работать (PostgreSQL available)
```

---

## 🔙 ЧАСТЬ 7: ROLLBACK PLAN

### 7.1 Rollback Steps

```bash
# 1. Stop new bot version
ssh Pi4-2 "sudo systemctl stop alex12060-bot"
ssh Pi4-2 "sudo systemctl stop alex12060-sync-worker"

# 2. Revert to old bot version (with SheetsService)
ssh Pi4-2 "cd Alex12060 && git checkout main"

# 3. Start old bot
ssh Pi4-2 "sudo systemctl start alex12060-bot"

# 4. Verify bot works with Google Sheets
ssh Pi4-2 "tail -f Alex12060/bot.log"

# 5. Keep PostgreSQL running (for future retry)
# Data is safe in PostgreSQL, can retry migration later
```

---

## 📈 ЧАСТЬ 8: ОЖИДАЕМЫЕ РЕЗУЛЬТАТЫ

| Метрика | До (Sheets) | После (PostgreSQL) | Улучшение |
|---------|-------------|-------------------|-----------|
| Создание смены | 2.5s | 0.05s | **98%** 🚀 |
| Редактирование | 0.8s | 0.01s | **99%** 🚀 |
| Просмотр истории | 1.0s | 0.005s | **99.5%** 🚀 |
| Расчет динам. ставки | 0.8s | 0.01s | **99%** 🚀 |
| Concurrent users | 5 | 1000+ | **200x** 🚀 |
| API calls к Sheets | 120/день | 0 | **100%** ⬇️ |
| Sync latency | N/A | 5-30s | Async |
| Downtime для миграции | 0 | 0 | Zero! |

---

## ✅ ЧАСТЬ 9: CHECKLIST ГОТОВНОСТИ

### Pre-Migration Checklist:

- [ ] PostgreSQL установлен и настроен
- [ ] База данных создана
- [ ] Все таблицы и индексы созданы
- [ ] Triggers настроены
- [ ] Migration script протестирован на копии данных
- [ ] Sync worker протестирован
- [ ] Мониторинг настроен
- [ ] Rollback plan готов
- [ ] Backup Google Sheets сделан
- [ ] Backup PostgreSQL настроен

### Post-Migration Checklist:

- [ ] Все данные мигрированы корректно
- [ ] Бот работает с PostgreSQL
- [ ] Sync worker синхронизирует в Google Sheets
- [ ] Мониторинг показывает здоровые метрики
- [ ] Google Sheets отображает актуальные данные
- [ ] Нет ошибок в логах
- [ ] Производительность соответствует ожиданиям

---

**Документ создан:** 2025-11-10
**Автор:** Claude Code (UltraThink Mode)
**Версия:** 1.0 FINAL
**Статус:** Ready for Implementation

**Следующий файл:** IMPLEMENTATION_PROMPTS.md с готовыми промптами для реализации
