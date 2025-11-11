# 🚀 ГОТОВЫЕ ПРОМПТЫ ДЛЯ ПОЭТАПНОЙ РЕАЛИЗАЦИИ

**Проект:** Alex12060 - Migration to PostgreSQL
**Дата:** 2025-11-10
**Цель:** Миграция с Google Sheets на PostgreSQL + асинхронная синхронизация

---

## 📋 КАК ИСПОЛЬЗОВАТЬ ЭТОТ ДОКУМЕНТ

1. Выполняй промпты **последовательно** (ЭТАП 1 → ЭТАП 2 → ... → ЭТАП 12)
2. После каждого этапа **тестируй** результат
3. Только после успешного тестирования переходи к следующему этапу
4. Каждый промпт **полностью автономный** - можно копировать и использовать отдельно
5. В каждом промпте указаны **файлы для создания** и **тесты для проверки**

---

## 🎯 ЭТАП 0: ПОДГОТОВКА (30 минут)

### ПРОМПТ 0.1: Установка PostgreSQL

```
Установи PostgreSQL на сервере Pi4-2 и подготовь базу данных для Alex12060 бота.

Требования:
1. Установить PostgreSQL 14+ через apt
2. Создать базу данных alex12060
3. Создать пользователя alex12060_user с паролем
4. Настроить права доступа
5. Включить autostart PostgreSQL

Команды выполняй через SSH на Pi4-2.

В конце выведи:
- Версию PostgreSQL
- Статус сервиса
- Список баз данных
- Тестовое подключение

Сохрани credentials в файл .env:
DB_HOST=localhost
DB_PORT=5432
DB_NAME=alex12060
DB_USER=alex12060_user
DB_PASSWORD=<generated_password>
```

**Тест успешности:**
```bash
ssh Pi4-2 "sudo systemctl status postgresql"
ssh Pi4-2 "psql -U alex12060_user -d alex12060 -c 'SELECT version();'"
```

---

### ПРОМПТ 0.2: Установка Python зависимостей

```
Установи необходимые Python библиотеки для работы с PostgreSQL.

Добавь в requirements.txt:
psycopg2-binary==2.9.9
sqlalchemy==2.0.23
alembic==1.12.1
asyncpg==0.29.0
prometheus-client==0.19.0

Установи зависимости в venv на сервере Pi4-2.
Проверь что импорты работают.
```

**Тест успешности:**
```bash
ssh Pi4-2 "cd Alex12060 && venv/bin/python3 -c 'import psycopg2; print(psycopg2.__version__)'"
ssh Pi4-2 "cd Alex12060 && venv/bin/python3 -c 'import sqlalchemy; print(sqlalchemy.__version__)'"
```

---

## 🗄️ ЭТАП 1: СОЗДАНИЕ СХЕМЫ БД (1-2 часа)

### ПРОМПТ 1.1: Создание основных таблиц

```
Создай SQL скрипт для инициализации схемы PostgreSQL базы данных Alex12060.

Используй полную схему из файла POSTGRESQL_ARCHITECTURE_DESIGN.md, раздел "2.1 PostgreSQL Schema".

Создай файл: migrations/001_initial_schema.sql

Включи в скрипт:
1. Все таблицы с правильными типами данных
2. Все constraints (CHECK, FOREIGN KEY, UNIQUE)
3. Все indexes для производительности
4. Комментарии для каждой таблицы

Таблицы в порядке зависимостей:
- employees
- products (с INSERT данных)
- shifts
- shift_products
- dynamic_rates
- ranks
- rank_bonuses
- active_bonuses
- employee_ranks
- sync_queue
- sync_log

Затем создай скрипт apply_migration.sh для применения миграции.

Протестируй что все таблицы созданы корректно.
```

**Тест успешности:**
```bash
ssh Pi4-2 "cd Alex12060 && psql -U alex12060_user -d alex12060 -f migrations/001_initial_schema.sql"
ssh Pi4-2 "psql -U alex12060_user -d alex12060 -c '\dt'"
```

---

### ПРОМПТ 1.2: Создание функций и триггеров

```
Создай SQL скрипт для функций и триггеров PostgreSQL.

Файл: migrations/002_functions_triggers.sql

Включи:

1. **Функцию add_to_sync_queue()**
   - Триггер для shifts
   - Триггер для active_bonuses
   - Триггер для employee_ranks

2. **Функцию refresh_employee_daily_sales()**
   - Триггер для автообновления materialized view

3. **Функцию get_dynamic_rate(sales_amount)**
   - Для быстрого получения ставки

4. **Функцию get_employee_rank(emp_id, year, month)**
   - Для определения ранга

5. **Materialized views**
   - employee_daily_sales
   - employee_monthly_sales

Полный код функций возьми из POSTGRESQL_ARCHITECTURE_DESIGN.md.

Примени миграцию и протестируй триггеры.
```

**Тест успешности:**
```bash
ssh Pi4-2 "psql -U alex12060_user -d alex12060 -f migrations/002_functions_triggers.sql"

# Тест триггера
ssh Pi4-2 "psql -U alex12060_user -d alex12060 -c \"
INSERT INTO employees (id, name) VALUES (1, 'Test User');
INSERT INTO shifts (date, employee_id, employee_name, clock_in, clock_out, worked_hours, total_sales, net_sales, commission_pct, total_per_hour, commissions, total_made)
VALUES (NOW(), 1, 'Test User', NOW(), NOW() + INTERVAL '8 hours', 8, 100, 80, 10, 120, 8, 128);
SELECT COUNT(*) FROM sync_queue;
\""
```

---

## 🔄 ЭТАП 2: СОЗДАНИЕ DB SERVICE (2-3 часа)

### ПРОМПТ 2.1: Базовый db_service.py

```
Создай новый файл db_service.py для работы с PostgreSQL базой данных.

Требования:

1. **Класс DatabaseService**
   - Connection pooling через psycopg2.pool
   - Методы для CRUD операций
   - Обработка ошибок
   - Logging

2. **Основные методы:**

```python
class DatabaseService:
    def __init__(self):
        """Initialize database connection pool."""
        pass

    # Employees
    def get_employee(self, employee_id: int) -> Optional[Dict]
    def get_employee_settings(self, employee_id: int) -> Dict
    def create_or_update_employee(self, employee_id: int, name: str)

    # Shifts
    def create_shift(self, shift_data: Dict) -> int
    def get_shift_by_id(self, shift_id: int) -> Optional[Dict]
    def get_last_shifts(self, employee_id: int, limit: int) -> List[Dict]
    def update_shift_field(self, shift_id: int, field: str, value: Any) -> bool

    # Products
    def get_products(self) -> List[Dict]
    def get_shift_products(self, shift_id: int) -> Dict[str, float]
    def set_shift_products(self, shift_id: int, products: Dict[str, float])

    # Dynamic rates
    def get_dynamic_rates(self) -> List[Dict]
    def calculate_dynamic_rate(self, employee_id: int, shift_date: str, current_sales: Decimal) -> float

    # Bonuses
    def get_active_bonuses(self, employee_id: int) -> List[Dict]
    def create_bonus(self, employee_id: int, bonus_type: str, value: float) -> int
    def apply_bonus(self, bonus_id: int, shift_id: int)

    # Ranks
    def get_ranks(self) -> List[Dict]
    def determine_rank(self, employee_id: int, year: int, month: int) -> str
```

3. **Используй SQL запросы с параметрами** (защита от injection)
4. **Connection context manager** для автоматического закрытия
5. **Декоратор @with_connection** для упрощения

Создай также файл db_models.py с TypedDict классами для типизации.

Не забудь про unit тесты!
```

**Тест успешности:**
```python
# test_db_service.py
from db_service import DatabaseService

db = DatabaseService()

# Test employee creation
db.create_or_update_employee(1, "Test Employee")
employee = db.get_employee(1)
assert employee['name'] == "Test Employee"

# Test shift creation
shift_data = {
    "date": "2025/11/10",
    "employee_id": 1,
    "employee_name": "Test Employee",
    "clock_in": "2025/11/10 09:00:00",
    "clock_out": "2025/11/10 17:00:00",
    "products": {"Bella": 100.50, "Laura": 75.25}
}
shift_id = db.create_shift(shift_data)
assert shift_id > 0

print("✅ All database tests passed!")
```

---

### ПРОМПТ 2.2: Интеграция в handlers.py

```
Обнови handlers.py для использования DatabaseService вместо SheetsService.

Требования:

1. **Создай файл db_service_adapter.py**
   - Адаптер чтобы DatabaseService имел тот же интерфейс что SheetsService
   - Это позволит минимально изменить handlers.py

```python
class DatabaseServiceAdapter:
    """Adapter to make DatabaseService compatible with SheetsService interface."""

    def __init__(self):
        self.db = DatabaseService()

    def get_worksheet(self):
        """Compatibility method - not used with PostgreSQL."""
        return None

    def create_shift(self, shift_data: Dict) -> int:
        """Create shift - delegates to DatabaseService."""
        return self.db.create_shift(shift_data)

    # ... остальные методы из SheetsService
```

2. **Обнови bot.py**
   - Замени SheetsService на DatabaseServiceAdapter
   - Добавь флаг USE_POSTGRESQL в config.py
   - При USE_POSTGRESQL=True используй DatabaseServiceAdapter
   - При USE_POSTGRESQL=False используй SheetsService (для rollback)

3. **Minimal changes в handlers.py**
   - Только изменить импорт
   - Остальной код должен работать без изменений

4. **Добавь логирование**
   - Логируй все database операции
   - Время выполнения запросов

Протестируй что бот работает с PostgreSQL.
```

**Тест успешности:**
```bash
# В config.py установи USE_POSTGRESQL=True
ssh Pi4-2 "cd Alex12060 && sudo systemctl restart alex12060-bot"
ssh Pi4-2 "tail -50 Alex12060/bot.log | grep -i postgres"

# Создай смену через бот и проверь что она в PostgreSQL
ssh Pi4-2 "psql -U alex12060_user -d alex12060 -c 'SELECT COUNT(*) FROM shifts;'"
```

---

## 🔄 ЭТАП 3: SYNC WORKER (3-4 часа)

### ПРОМПТ 3.1: Базовый Sync Worker

```
Создай Sync Worker для асинхронной синхронизации PostgreSQL → Google Sheets.

Файл: sheets_sync_worker.py

Требования:

1. **Класс SheetsSyncWorker**

```python
class SheetsSyncWorker:
    def __init__(self):
        """Initialize sync worker."""
        self.running = True
        self.db_conn = None  # PostgreSQL connection
        self.sheets_client = None  # Google Sheets client
        self.batch_size = 10
        self.sync_interval = 5  # seconds

    async def run(self):
        """Main worker loop."""
        while self.running:
            items = self.get_pending_sync_items()
            if items:
                await self.process_sync_batch(items)
            await asyncio.sleep(self.sync_interval)

    def get_pending_sync_items(self) -> List[Dict]:
        """Get pending items from sync_queue."""
        # SQL query to sync_queue

    async def process_sync_batch(self, items: List[Dict]):
        """Process batch of sync items."""
        for item in items:
            await self.sync_to_sheets(item)

    async def sync_to_sheets(self, item: Dict) -> bool:
        """Sync single item to Google Sheets."""
        if item['table_name'] == 'shifts':
            return await self.sync_shift(item['operation'], item['data'])
        elif item['table_name'] == 'active_bonuses':
            return await self.sync_bonus(item['operation'], item['data'])
        # ...

    async def sync_shift(self, operation: str, shift_data: Dict) -> bool:
        """Sync shift to Shifts worksheet."""
        # INSERT, UPDATE, или DELETE в Google Sheets

    def build_shift_row(self, shift_data: Dict, products: Dict) -> List:
        """Build row for Google Sheets in correct format."""
        # Формат должен совпадать с текущей структурой Sheets
```

2. **Signal handlers** для graceful shutdown
3. **Retry logic** с exponential backoff
4. **Error handling** для Google API rate limits
5. **Logging** всех операций синхронизации

6. **Проверь формат Google Sheets**
   - ID, Date, EmployeeId, EmployeeName, Clock in/out
   - Все products (Bella, Laura, Sophie, Alice, Emma, Molly, Other)
   - Total sales, Net sales, %, Total per hour, Commissions, Total made
   - Порядок столбцов должен совпадать с текущим!

Используй async/await для неблокирующих операций.
```

**Тест успешности:**
```bash
# Запусти worker вручную
ssh Pi4-2 "cd Alex12060 && venv/bin/python3 sheets_sync_worker.py &"

# Создай смену через бот
# Проверь что она появилась в Google Sheets через 5-30 секунд

# Проверь логи worker
ssh Pi4-2 "tail -f Alex12060/sync_worker.log"

# Проверь sync_queue
ssh Pi4-2 "psql -U alex12060_user -d alex12060 -c 'SELECT status, COUNT(*) FROM sync_queue GROUP BY status;'"
```

---

### ПРОМПТ 3.2: Bidirectional Sync (справочники)

```
Добавь в Sync Worker синхронизацию справочников Google Sheets → PostgreSQL.

Требования:

1. **Метод sync_reference_data_from_sheets()**

```python
async def sync_reference_data_from_sheets(self):
    """Периодическая синхронизация справочников из Sheets."""
    while self.running:
        try:
            await self.sync_employee_settings_from_sheets()
            await self.sync_dynamic_rates_from_sheets()
            await self.sync_ranks_from_sheets()

            logger.info("Reference data synced from Sheets")
        except Exception as e:
            logger.error(f"Error syncing from Sheets: {e}")

        await asyncio.sleep(300)  # каждые 5 минут

async def sync_employee_settings_from_sheets(self):
    """Sync EmployeeSettings worksheet → employees table."""
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

# Аналогично для DynamicRates и Ranks
```

2. **Запускай sync_reference_data_from_sheets() в отдельном task**

3. **Cache invalidation**
   - После обновления справочников инвалидируй кэш в боте
   - Используй Redis или простой флаг в PostgreSQL

4. **Conflict resolution**
   - Sheets всегда wins для справочников
   - PostgreSQL wins для транзакционных данных

Протестируй bidirectional sync.
```

**Тест успешности:**
```bash
# 1. Измени Hourly wage в EmployeeSettings в Google Sheets
# 2. Подожди 5 минут
# 3. Проверь что изменение попало в PostgreSQL

ssh Pi4-2 "psql -U alex12060_user -d alex12060 -c \"
SELECT id, hourly_wage, base_commission FROM employees;
\""

# 4. Создай смену и проверь что используется новая ставка
```

---

### ПРОМПТ 3.3: Systemd Service для Sync Worker

```
Создай systemd service для Sync Worker.

Файл: alex12060-sync-worker.service

```ini
[Unit]
Description=Alex12060 Sheets Sync Worker
After=network.target postgresql.service alex12060-bot.service
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

Установи и запусти service:

```bash
scp alex12060-sync-worker.service Pi4-2:/tmp/
ssh Pi4-2 "sudo mv /tmp/alex12060-sync-worker.service /etc/systemd/system/"
ssh Pi4-2 "sudo systemctl daemon-reload"
ssh Pi4-2 "sudo systemctl enable alex12060-sync-worker"
ssh Pi4-2 "sudo systemctl start alex12060-sync-worker"
```

Проверь что worker работает корректно.
```

**Тест успешности:**
```bash
ssh Pi4-2 "sudo systemctl status alex12060-sync-worker"
ssh Pi4-2 "sudo journalctl -u alex12060-sync-worker -f"
ssh Pi4-2 "tail -f Alex12060/sync_worker.log"
```

---

## 🔀 ЭТАП 4: МИГРАЦИЯ ДАННЫХ (2-3 часа)

### ПРОМПТ 4.1: Создание Migration Script

```
Создай скрипт для миграции существующих данных из Google Sheets в PostgreSQL.

Файл: migrate_sheets_to_postgres.py

Требования:

1. **Класс SheetsMigration**

```python
class SheetsMigration:
    def __init__(self):
        self.sheets_client = gspread.service_account(...)
        self.db_conn = psycopg2.connect(...)
        self.id_mapping = {}  # Sheets ID → PostgreSQL ID

    def run_migration(self):
        """Run full migration."""
        logger.info("Starting migration...")

        try:
            # Step 1: Backup
            self.backup_sheets_data()

            # Step 2: Migrate reference data
            self.migrate_products()
            self.migrate_employee_settings()
            self.migrate_dynamic_rates()
            self.migrate_ranks()

            # Step 3: Migrate transactional data
            self.migrate_employees()
            self.migrate_shifts()
            self.migrate_active_bonuses()
            self.migrate_employee_ranks()

            # Step 4: Verify
            self.verify_migration()

            logger.info("✅ Migration completed!")

        except Exception as e:
            logger.error(f"❌ Migration failed: {e}")
            self.db_conn.rollback()
            raise

    def migrate_shifts(self):
        """Migrate Shifts table."""
        ws = self.spreadsheet.worksheet('Shifts')
        records = ws.get_all_records()

        for record in records:
            # Parse dates with time_utils
            shift_data = {
                'sheets_id': record['ID'],
                'date': parse_dt(record['Date']),
                'employee_id': record['EmployeeId'],
                # ... все поля
            }

            # Insert into PostgreSQL
            shift_id = self.db.create_shift(shift_data)
            self.id_mapping['shifts'][record['ID']] = shift_id

            # Insert products
            for product in ['Bella', 'Laura', ...]:
                amount = record.get(product, 0)
                if amount and float(amount) > 0:
                    self.db.set_shift_product(shift_id, product, amount)

    def verify_migration(self):
        """Verify counts match."""
        # Compare counts PostgreSQL vs Sheets
        # Log any discrepancies
```

2. **Backup перед миграцией**
   - Экспортируй все worksheets в JSON
   - Сохрани в backup/migration_YYYY-MM-DD_HH-MM-SS/

3. **Dry-run mode**
   - Флаг --dry-run для тестирования без записи

4. **Progress bar**
   - Используй tqdm для отображения прогресса

5. **Детальное логирование**

Протестируй на копии данных первым делом!
```

**Тест успешности:**
```bash
# Dry-run
ssh Pi4-2 "cd Alex12060 && venv/bin/python3 migrate_sheets_to_postgres.py --dry-run"

# Real migration
ssh Pi4-2 "cd Alex12060 && venv/bin/python3 migrate_sheets_to_postgres.py"

# Verify
ssh Pi4-2 "psql -U alex12060_user -d alex12060 -c \"
SELECT
  'shifts' as table, COUNT(*) as count FROM shifts
UNION ALL
SELECT 'products' as table, COUNT(*) FROM shift_products
UNION ALL
SELECT 'bonuses' as table, COUNT(*) FROM active_bonuses;
\""
```

---

### ПРОМПТ 4.2: Rollback Script

```
Создай rollback скрипт на случай если нужно откатиться.

Файл: rollback_migration.sh

```bash
#!/bin/bash

# Rollback to Google Sheets mode

echo "🔙 Rolling back to Google Sheets mode..."

# 1. Stop services
echo "Stopping services..."
sudo systemctl stop alex12060-bot
sudo systemctl stop alex12060-sync-worker

# 2. Switch config
echo "Switching to Sheets mode..."
sed -i 's/USE_POSTGRESQL=True/USE_POSTGRESQL=False/g' .env

# 3. Restart bot with Sheets
echo "Restarting bot..."
sudo systemctl start alex12060-bot

# 4. Verify
echo "Verifying..."
sleep 5
sudo systemctl status alex12060-bot

echo "✅ Rollback completed. Bot is using Google Sheets again."
echo "PostgreSQL data is preserved for future retry."
```

Сделай скрипт исполняемым и протестируй.
```

**Тест успешности:**
```bash
ssh Pi4-2 "cd Alex12060 && chmod +x rollback_migration.sh"
ssh Pi4-2 "cd Alex12060 && ./rollback_migration.sh"
ssh Pi4-2 "tail -30 Alex12060/bot.log"
```

---

## 📊 ЭТАП 5: МОНИТОРИНГ (2 часа)

### ПРОМПТ 5.1: Prometheus Metrics

```
Добавь мониторинг с Prometheus metrics.

Файл: metrics.py

```python
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
    ['table', 'status']
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

# Start metrics server on port 9090
start_http_server(9090)
```

Интегрируй metrics в:
1. db_service.py - декоратор @track_query_time
2. sheets_sync_worker.py - track sync operations
3. handlers.py - track bot operations

Запусти metrics server и проверь http://Pi4-2:9090/metrics
```

**Тест успешности:**
```bash
ssh Pi4-2 "curl http://localhost:9090/metrics | grep alex12060"
```

---

### ПРОМПТ 5.2: Grafana Dashboard

```
Создай Grafana dashboard для мониторинга.

Файл: grafana_dashboard.json

Dashboard должен включать:

1. **Sync Queue Panel**
   - Размер очереди по статусам (pending, processing, failed)
   - График за последний час

2. **Bot Performance Panel**
   - Response time (p50, p95, p99)
   - Operations per minute
   - Error rate

3. **Database Performance Panel**
   - Query duration (p50, p95, p99)
   - Active connections
   - Slow queries (>1s)

4. **Sync Performance Panel**
   - Sync latency
   - Success/failure rate
   - Items synced per minute

5. **System Resources Panel**
   - CPU usage
   - Memory usage
   - Disk I/O

Создай dashboard config и инструкцию для импорта в Grafana.
```

**Тест успешности:**
- Import dashboard в Grafana
- Проверить что все панели показывают данные
- Создать alert правила для критичных метрик

---

## ✅ ЭТАП 6: ТЕСТИРОВАНИЕ (3-4 часа)

### ПРОМПТ 6.1: Unit Tests

```
Создай comprehensive unit tests для всех компонентов.

Файлы:
- tests/test_db_service.py
- tests/test_sync_worker.py
- tests/test_migration.py

Используй pytest с fixtures для:
- Test database (отдельная БД для тестов)
- Mock Google Sheets API
- Test data generators

Покрытие должно быть >80%.

Примеры тестов:

```python
# test_db_service.py

def test_create_shift(db_service, test_employee):
    shift_data = generate_test_shift(test_employee['id'])
    shift_id = db_service.create_shift(shift_data)
    assert shift_id > 0

    shift = db_service.get_shift_by_id(shift_id)
    assert shift['employee_id'] == test_employee['id']
    assert shift['total_sales'] == shift_data['total_sales']

def test_dynamic_rate_calculation(db_service, test_employee):
    # Test rate calculation based on sales
    rate = db_service.calculate_dynamic_rate(test_employee['id'], '2025/11/10', Decimal('100'))
    assert rate >= 0
    assert rate <= 100

# test_sync_worker.py

async def test_sync_shift_to_sheets(sync_worker, test_shift, mock_sheets):
    success = await sync_worker.sync_shift('INSERT', test_shift)
    assert success == True
    assert mock_sheets.append_row.called

def test_batch_processing(sync_worker, mock_db):
    items = mock_db.get_pending_sync_items()
    assert len(items) <= sync_worker.batch_size
```

Запусти тесты и убедись что все проходят.
```

**Тест успешности:**
```bash
ssh Pi4-2 "cd Alex12060 && venv/bin/pytest tests/ -v --cov=. --cov-report=html"
```

---

### ПРОМПТ 6.2: Integration Tests

```
Создай integration tests для end-to-end сценариев.

Файл: tests/test_integration.py

Тесты должны проверять:

1. **Full shift lifecycle**
```python
async def test_full_shift_lifecycle():
    # 1. Create shift through bot
    shift_id = bot.create_shift_via_telegram(user_id, shift_data)

    # 2. Verify in PostgreSQL
    shift = db.get_shift_by_id(shift_id)
    assert shift is not None

    # 3. Wait for sync
    await asyncio.sleep(30)

    # 4. Verify in Google Sheets
    sheets_row = sheets.find_shift_by_id(shift_id)
    assert sheets_row is not None
    assert sheets_row['Total sales'] == shift['total_sales']

    # 5. Edit shift
    bot.edit_shift_total_sales(shift_id, new_total=200)

    # 6. Verify update propagated
    await asyncio.sleep(30)
    sheets_row_updated = sheets.find_shift_by_id(shift_id)
    assert sheets_row_updated['Total sales'] == '200.00'
```

2. **Bonus application**
3. **Rank calculation**
4. **Reference data sync (Sheets → PostgreSQL)**
5. **Failover scenarios**

Запусти integration tests в staging environment.
```

**Тест успешности:**
```bash
ssh Pi4-2 "cd Alex12060 && venv/bin/pytest tests/test_integration.py -v -s"
```

---

### ПРОМПТ 6.3: Load Testing

```
Создай load test для проверки производительности под нагрузкой.

Файл: tests/test_load.py

Используй locust или pytest-benchmark.

```python
from locust import HttpUser, task, between

class BotUser(HttpUser):
    wait_time = between(1, 3)

    @task(3)
    def create_shift(self):
        """Simulate shift creation."""
        shift_data = generate_random_shift()
        response = self.client.post('/api/shifts', json=shift_data)
        assert response.status_code == 200

    @task(1)
    def get_history(self):
        """Simulate history request."""
        employee_id = random.randint(1, 10)
        response = self.client.get(f'/api/shifts?employee_id={employee_id}')
        assert response.status_code == 200
```

Тесты:
1. 10 concurrent users
2. 50 concurrent users
3. 100 concurrent users

Измерь:
- Response time (p50, p95, p99)
- Throughput (requests/sec)
- Error rate
- Database load

Убедись что производительность соответствует ожиданиям (смотри таблицу в POSTGRESQL_ARCHITECTURE_DESIGN.md).
```

**Тест успешности:**
```bash
ssh Pi4-2 "cd Alex12060 && locust -f tests/test_load.py --host=http://localhost:8080"
```

---

## 🚀 ЭТАП 7: PRODUCTION DEPLOYMENT (1-2 часа)

### ПРОМПТ 7.1: Pre-Deployment Checklist

```
Выполни pre-deployment checklist перед миграцией в production.

Создай файл: deployment_checklist.md

Checklist:

**Infrastructure:**
- [ ] PostgreSQL установлен и настроен
- [ ] Все миграции применены
- [ ] Indexes созданы
- [ ] Triggers работают
- [ ] Backup PostgreSQL настроен (ежедневный)

**Application:**
- [ ] Все unit tests проходят (100%)
- [ ] Все integration tests проходят
- [ ] Load tests показывают приемлемую производительность
- [ ] Логирование настроено
- [ ] Мониторинг работает

**Data:**
- [ ] Backup Google Sheets сделан
- [ ] Migration script протестирован на копии данных
- [ ] Dry-run миграции прошел успешно
- [ ] Rollback script готов и протестирован

**Services:**
- [ ] alex12060-bot.service обновлен
- [ ] alex12060-sync-worker.service создан и протестирован
- [ ] Оба service включены в autostart

**Documentation:**
- [ ] POSTGRESQL_ARCHITECTURE_DESIGN.md актуален
- [ ] IMPLEMENTATION_PROMPTS.md актуален
- [ ] CLAUDE.md обновлен
- [ ] README обновлен

**Monitoring:**
- [ ] Prometheus metrics доступны
- [ ] Grafana dashboard создан
- [ ] Alerts настроены

Пройдись по чеклисту и отметь что выполнено.
Если что-то не готово - вернись к соответствующему этапу.
```

---

### ПРОМПТ 7.2: Production Migration

```
Выполни миграцию в production.

План:

1. **Подготовка (за 1 день до миграции)**

```bash
# Сделай backup Google Sheets
ssh Pi4-2 "cd Alex12060 && venv/bin/python3 backup_sheets.py"

# Сделай backup текущего кода
ssh Pi4-2 "cd Alex12060 && git branch backup-pre-postgres && git push origin backup-pre-postgres"

# Проверь что все готово
ssh Pi4-2 "cd Alex12060 && cat deployment_checklist.md"
```

2. **Migration Day (выбери время низкой активности)**

```bash
# Step 1: Notify users (если есть группа)
# Отправь сообщение что будет короткий downtime (5-10 минут)

# Step 2: Stop bot
ssh Pi4-2 "sudo systemctl stop alex12060-bot"

# Step 3: Switch to PostgreSQL mode
ssh Pi4-2 "cd Alex12060 && echo 'USE_POSTGRESQL=True' >> .env"

# Step 4: Run migration
ssh Pi4-2 "cd Alex12060 && venv/bin/python3 migrate_sheets_to_postgres.py 2>&1 | tee migration.log"

# Step 5: Verify migration
ssh Pi4-2 "cd Alex12060 && venv/bin/python3 verify_migration.py"

# Step 6: Start services
ssh Pi4-2 "sudo systemctl start alex12060-bot"
ssh Pi4-2 "sudo systemctl start alex12060-sync-worker"

# Step 7: Verify both services are running
ssh Pi4-2 "sudo systemctl status alex12060-bot"
ssh Pi4-2 "sudo systemctl status alex12060-sync-worker"

# Step 8: Test bot manually
# Отправь /start боту
# Создай тестовую смену
# Проверь что она появилась в PostgreSQL
# Проверь что она синхронизировалась в Google Sheets (через 30 сек)

# Step 9: Monitor logs
ssh Pi4-2 "tail -f Alex12060/bot.log Alex12060/sync_worker.log"
```

3. **Post-Migration (первые 24 часа)**

```bash
# Мониторь метрики каждые 2 часа
# Проверяй sync_queue что не накапливается backlog
# Проверяй что нет ошибок в логах

ssh Pi4-2 "psql -U alex12060_user -d alex12060 -c \"
SELECT status, COUNT(*) FROM sync_queue GROUP BY status;
\""
```

4. **Rollback (если что-то пошло не так)**

```bash
ssh Pi4-2 "cd Alex12060 && ./rollback_migration.sh"
```

Выполни миграцию согласно плану.
После успешной миграции отметь в логе время и результаты.
```

**Тест успешности:**
- Бот отвечает на команды
- Смены создаются быстро (<0.1s)
- Sync worker синхронизирует в Sheets
- Нет ошибок в логах
- Метрики показывают здоровое состояние

---

### ПРОМПТ 7.3: Post-Migration Monitoring

```
Настрой post-migration мониторинг.

Создай скрипт: monitoring/post_migration_check.sh

```bash
#!/bin/bash

echo "📊 Post-Migration Health Check"
echo "================================"

# Check services
echo "1. Services status:"
ssh Pi4-2 "systemctl is-active alex12060-bot alex12060-sync-worker"

# Check sync queue
echo -e "\n2. Sync queue:"
ssh Pi4-2 "psql -U alex12060_user -d alex12060 -c \"
SELECT status, COUNT(*) as count, MAX(created_at) as last_created
FROM sync_queue
GROUP BY status;
\""

# Check recent errors
echo -e "\n3. Recent errors:"
ssh Pi4-2 "tail -100 Alex12060/bot.log | grep -i error | tail -5"
ssh Pi4-2 "tail -100 Alex12060/sync_worker.log | grep -i error | tail -5"

# Check performance
echo -e "\n4. Performance metrics:"
ssh Pi4-2 "curl -s http://localhost:9090/metrics | grep -E '(bot_response_time|sync_duration|db_query_duration)' | grep quantile | tail -10"

# Check database size
echo -e "\n5. Database size:"
ssh Pi4-2 "psql -U alex12060_user -d alex12060 -c \"
SELECT
    schemaname,
    tablename,
    pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) AS size
FROM pg_tables
WHERE schemaname = 'public'
ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC
LIMIT 10;
\""

echo -e "\n✅ Health check completed"
```

Запускай этот скрипт каждые 2 часа в первые 24 часа после миграции.
```

**Тест успешности:**
```bash
chmod +x monitoring/post_migration_check.sh
./monitoring/post_migration_check.sh
```

---

## 📚 ЭТАП 8: ДОКУМЕНТАЦИЯ (1 час)

### ПРОМПТ 8.1: Обновление документации

```
Обнови всю проектную документацию после успешной миграции.

Файлы для обновления:

1. **CLAUDE.md**
   - Добавь секцию "PostgreSQL Migration"
   - Обнови секцию "Архитектура"
   - Добавь новые команды для управления
   - Обнови troubleshooting guide

2. **README.md**
   - Обнови описание архитектуры
   - Добавь инструкции по PostgreSQL
   - Обнови installation guide

3. **DATABASE_ARCHITECTURE.md** (новый файл)
   - Описание схемы PostgreSQL
   - ER diagram
   - Описание indexes и их назначение
   - Query performance tips

4. **SYNC_WORKER.md** (новый файл)
   - Как работает sync worker
   - Конфигурация
   - Troubleshooting
   - Monitoring

5. **MIGRATION_GUIDE.md** (новый файл)
   - Detailed migration steps
   - Rollback procedure
   - Post-migration checklist
   - Common issues and solutions

Обнови все ссылки между документами.
Убедись что документация актуальна и полная.
```

---

### ПРОМПТ 8.2: Создание Runbook

```
Создай operational runbook для production support.

Файл: RUNBOOK.md

Включи:

1. **Обычные операции**
   - Как перезапустить bot
   - Как перезапустить sync worker
   - Как проверить статус системы
   - Как просмотреть логи

2. **Troubleshooting**
   - Bot не отвечает
   - Sync worker не синхронизирует
   - PostgreSQL недоступен
   - Google Sheets API rate limit
   - Sync queue растет

3. **Emergency procedures**
   - Как сделать rollback к Google Sheets
   - Как восстановить из backup
   - Как очистить sync queue
   - Контакты для escalation

4. **Monitoring**
   - Какие метрики смотреть
   - Пороги для alerts
   - Где смотреть logs

5. **Maintenance**
   - Как делать backup
   - Как применять updates
   - Как обновлять справочники
   - Как чистить старые данные

Сделай runbook понятным для не-технического персонала.
```

---

## 🎉 ФИНАЛЬНАЯ ПРОВЕРКА

### ПРОМПТ FINAL: Комплексная проверка

```
Выполни финальную комплексную проверку всей системы.

Checklist:

**Functionality (через Telegram бот):**
- [ ] Создание смены работает быстро (<0.1s)
- [ ] Редактирование смены работает
- [ ] Просмотр истории работает
- [ ] Применение бонусов работает
- [ ] Расчет рангов работает
- [ ] Все команды бота отвечают

**Data Integrity:**
- [ ] Все смены из Sheets мигрированы в PostgreSQL
- [ ] Все смены синхронизированы обратно в Sheets
- [ ] Данные в Sheets совпадают с PostgreSQL
- [ ] Нет потерянных записей
- [ ] ID mapping корректный

**Performance:**
- [ ] Создание смены <0.1s (PostgreSQL)
- [ ] Sync latency <30s (PostgreSQL → Sheets)
- [ ] Нет slow queries (>1s)
- [ ] Memory usage в пределах нормы
- [ ] CPU usage в пределах нормы

**Monitoring:**
- [ ] Prometheus metrics доступны
- [ ] Grafana dashboard показывает данные
- [ ] Alerts настроены
- [ ] Логи пишутся корректно

**Services:**
- [ ] alex12060-bot.service running и enabled
- [ ] alex12060-sync-worker.service running и enabled
- [ ] PostgreSQL running и enabled
- [ ] Все service перезапускаются после reboot

**Documentation:**
- [ ] Вся документация актуальна
- [ ] Runbook готов
- [ ] Migration guide полный
- [ ] Troubleshooting guide обновлен

Если все галочки стоят - миграция успешна! 🎉

Создай файл MIGRATION_SUCCESS.md с:
- Датой и временем миграции
- Финальными метриками производительности
- Известными issues (если есть)
- Планами на улучшение
```

---

## 📊 SUMMARY: ПОРЯДОК ВЫПОЛНЕНИЯ

| Этап | Время | Критичность | Зависимости |
|------|-------|-------------|-------------|
| 0. Подготовка | 30 мин | HIGH | - |
| 1. Схема БД | 1-2 часа | HIGH | Этап 0 |
| 2. DB Service | 2-3 часа | HIGH | Этап 1 |
| 3. Sync Worker | 3-4 часа | HIGH | Этапы 1, 2 |
| 4. Миграция данных | 2-3 часа | HIGH | Этапы 1, 2, 3 |
| 5. Мониторинг | 2 часа | MEDIUM | Этапы 2, 3 |
| 6. Тестирование | 3-4 часа | HIGH | Все предыдущие |
| 7. Production | 1-2 часа | HIGH | Все предыдущие |
| 8. Документация | 1 час | MEDIUM | Этап 7 |

**Общее время:** 15-22 часа (разбить на 3-4 дня)

---

## 🚨 ВАЖНЫЕ ЗАМЕЧАНИЯ

1. **НЕ пропускай тестирование!** Каждый этап должен быть протестирован.

2. **Делай backup перед каждым значимым изменением.**

3. **Используй git branches:**
   - `main` - стабильная версия с Sheets
   - `feature/postgresql` - разработка PostgreSQL
   - `staging` - тестирование перед production

4. **Rollback plan всегда должен быть готов.**

5. **Мониторь производительность на каждом этапе.**

6. **Документируй все изменения и решения.**

7. **Не торопись - лучше потратить больше времени на тестирование, чем потом чинить в production.**

---

## 📞 SUPPORT

При возникновении проблем:
1. Проверь логи: `tail -f bot.log sync_worker.log`
2. Проверь metrics: `curl http://localhost:9090/metrics`
3. Проверь sync_queue: `SELECT * FROM sync_queue WHERE status='failed'`
4. Посмотри RUNBOOK.md для troubleshooting
5. При необходимости сделай rollback: `./rollback_migration.sh`

---

**Файл создан:** 2025-11-10
**Автор:** Claude Code
**Версия:** 1.0 FINAL
**Статус:** READY TO USE

**Начинай с ЭТАПА 0 и следуй последовательно!** 🚀
