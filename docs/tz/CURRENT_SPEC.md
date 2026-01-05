# Alex12060 - Текущая Спецификация

**Версия:** 4.0.0
**Дата:** 2025-12-19
**Статус:** Production

---

## Обзор системы

Alex12060 - Telegram бот для управления рабочими сменами сотрудников с автоматическим расчётом зарплаты, комиссий и бонусов.

**Архитектура:**
- PostgreSQL - primary database (source of truth)
- Google Sheets - read-only mirror для визуализации
- Асинхронная синхронизация каждые 5 минут

---

## Основные функции

### 1. Управление сменами
- **Clock in** - начало смены (выбор даты и времени)
- **Clock out** - окончание смены
- **Редактирование** - изменение времени и продаж
- **История** - просмотр последних смен

### 2. Учёт продаж
- 4 продукта: Model A, Model B, Model C, Model D
- Ввод суммы продаж по каждому продукту
- Расчёт net_sales = total_sales × 0.8

### 3. Комиссии
- **Base commission** - базовая ставка сотрудника (default 8%)
- **Dynamic commission** - зависит от продаж за смену
- **Bonus commission** - от повышения ранга

### 4. Rolling Average & Bonus Counter
- **Rolling Average** - взвешенное среднее продаж за последние 7 смен
- **Bonus Counter** - флаг, если продажи >= rolling_average

### 5. Fortnights (Двухнедельные периоды)
- Период 1: дни 1-15 месяца
- Период 2: дни 16-31 месяца
- Агрегация заработка по периодам

### 6. Система рангов
- 6 рангов на основе месячных продаж
- Автоматическое начисление бонусов при повышении

### 7. Синхронизация
- PostgreSQL → Google Sheets
- 5 листов с разным количеством колонок

---

## База данных PostgreSQL

### Таблицы (17)

| Таблица | Описание | Ключевые поля |
|---------|----------|---------------|
| `employees` | Сотрудники | id (=telegram_id), hourly_wage, sales_commission |
| `shifts` | Смены | date, clock_in/out, total_sales, rolling_average, bonus_counter |
| `products` | Продукты | name (Model A, B, C, D) |
| `shift_products` | Продажи по продуктам | shift_id, product_id, amount |
| `employee_fortnights` | Зарплата по периодам | year, month, fortnight_number, total_earnings |
| `ranks` | Определения рангов | name, min_amount, max_amount |
| `employee_ranks` | Ранги сотрудников | employee_id, year, month, current_rank_id |
| `rank_bonuses` | Бонусы за ранги | rank_id, bonus_code |
| `active_bonuses` | Активные бонусы | employee_id, bonus_type, value, applied |
| `dynamic_rates` | Динамические ставки | min_amount, max_amount, percentage |
| `base_commissions` | Tier комиссии | tier_name, min_sales, max_sales, percentage |
| `bonus_settings` | Настройки бонусов | setting_name, setting_value |
| `sync_queue` | Очередь синхронизации | table_name, record_id, operation, status |

---

## Ключевые расчёты

### 1. Rolling Average (7 смен)

```python
def calculate_rolling_average(employee_id, shift_date):
    """
    Взвешенное среднее за последние 7 смен ДО текущей.
    Текущая смена НЕ входит в расчёт.
    """
    # Получить последние 7 смен
    shifts = SELECT total_sales FROM shifts
             WHERE employee_id = ? AND date < shift_date
             ORDER BY date DESC, clock_in DESC
             LIMIT 7

    # Развернуть (от старых к новым)
    shifts = reversed(shifts)

    # Веса: position (1 = oldest, N = newest)
    weighted_sum = sum(i * sales for i, sales in enumerate(shifts, 1))
    weight_sum = sum(range(1, len(shifts) + 1))

    return weighted_sum / weight_sum if weight_sum > 0 else 0
```

**Пример:**
```
Смены (от старой к новой): $100, $200, $300, $400, $500
Веса:                       1,    2,    3,    4,    5
Weighted sum = 1×100 + 2×200 + 3×300 + 4×400 + 5×500 = 5500
Weight sum = 1 + 2 + 3 + 4 + 5 = 15
Rolling average = 5500 / 15 = $366.67
```

### 2. Bonus Counter

```python
bonus_counter = (total_sales >= rolling_average)
# TRUE если продажи текущей смены >= rolling_average
# FALSE в противном случае
```

### 3. Commission Breakdown

```python
# Base commission (из настроек сотрудника)
base_pct = employee.sales_commission  # default 8%

# Dynamic commission (по продажам смены)
dynamic_pct = get_dynamic_rate(total_sales)
# $0-400: 0%, $400-700: 1%, $700-1000: 2%, $1000+: 3%

# Bonus commission (от повышения ранга)
bonus_pct = sum(active_bonuses where type='percent_*')

# Total commission %
commission_pct = base_pct + dynamic_pct + bonus_pct

# Расчёт заработка
total_hourly = worked_hours × hourly_wage
commissions = net_sales × commission_pct / 100
flat_bonuses = sum(active_bonuses where type='flat_*')
total_made = total_hourly + commissions + flat_bonuses
```

### 4. Fortnights

```python
# Определение периода
if day <= 15:
    fortnight_number = 1
    start_date = f"{year}-{month:02d}-01"
    end_date = f"{year}-{month:02d}-15"
else:
    fortnight_number = 2
    start_date = f"{year}-{month:02d}-16"
    end_date = last_day_of_month(year, month)

# Агрегация
total_shifts = count(shifts in period)
total_hours = sum(worked_hours)
hourly_earnings = total_hours × hourly_wage
total_sales = sum(total_sales)
net_sales = sum(net_sales)
base_commission = sum(base portion of commissions)
dynamic_commission = sum(dynamic portion)
bonus_commission = sum(bonus portion)
total_commissions = base + dynamic + bonus
total_earnings = hourly_earnings + total_commissions
```

---

## Google Sheets - Структура листов

### 1. Shifts (19 колонок)

| # | Колонка | Тип | Описание |
|---|---------|-----|----------|
| A | ID | INT | ID смены |
| B | Date | DATE | Дата смены |
| C | EmployeeID | BIGINT | Telegram ID |
| D | EmployeeName | STRING | Имя сотрудника |
| E | ClockIn | DATETIME | Время начала |
| F | ClockOut | DATETIME | Время окончания |
| G | WorkedHours | DECIMAL | Отработано часов |
| H | ModelA | DECIMAL | Продажи Model A |
| I | ModelB | DECIMAL | Продажи Model B |
| J | ModelC | DECIMAL | Продажи Model C |
| K | ModelD | DECIMAL | Продажи Model D |
| L | TotalSales | DECIMAL | Общие продажи |
| M | NetSales | DECIMAL | Чистые продажи (×0.8) |
| N | CommissionPct | DECIMAL | % комиссии |
| O | TotalHourly | DECIMAL | Почасовая оплата |
| P | Commissions | DECIMAL | Комиссионные |
| Q | TotalMade | DECIMAL | Итого заработок |
| R | RollingAverage | DECIMAL | Скользящее среднее |
| S | BonusCounter | BOOLEAN | Флаг превышения |

### 2. ActiveBonuses (7 колонок)

| # | Колонка | Тип | Описание |
|---|---------|-----|----------|
| A | ID | INT | ID бонуса |
| B | EmployeeID | BIGINT | Telegram ID |
| C | BonusType | STRING | Тип бонуса |
| D | Value | DECIMAL | Значение |
| E | Applied | BOOLEAN | Применён ли |
| F | ShiftID | INT | К какой смене применён |
| G | CreatedAt | DATETIME | Дата создания |

### 3. EmployeeRanks (7 колонок)

| # | Колонка | Тип | Описание |
|---|---------|-----|----------|
| A | EmployeeID | BIGINT | Telegram ID |
| B | Year | INT | Год |
| C | Month | INT | Месяц |
| D | CurrentRank | STRING | Текущий ранг |
| E | PreviousRank | STRING | Предыдущий ранг |
| F | UpdatedAt | DATETIME | Дата обновления |
| G | Notified | BOOLEAN | Уведомлён ли |

### 4. EmployeeSettings (5 колонок)

| # | Колонка | Тип | Описание |
|---|---------|-----|----------|
| A | TelegramID | BIGINT | Telegram ID |
| B | Name | STRING | Имя |
| C | HourlyWage | DECIMAL | Почасовая ставка |
| D | SalesCommission | DECIMAL | Базовая комиссия % |
| E | ID | BIGINT | ID записи |

### 5. EmployeeFortnights (18 колонок)

| # | Колонка | Тип | Описание |
|---|---------|-----|----------|
| A | ID | INT | ID записи |
| B | EmployeeID | BIGINT | Telegram ID |
| C | Year | INT | Год |
| D | Month | INT | Месяц |
| E | FortnightNumber | INT | Номер периода (1 или 2) |
| F | StartDate | DATE | Начало периода |
| G | EndDate | DATE | Конец периода |
| H | TotalShifts | INT | Количество смен |
| I | TotalHours | DECIMAL | Всего часов |
| J | HourlyEarnings | DECIMAL | Почасовой заработок |
| K | TotalSales | DECIMAL | Общие продажи |
| L | NetSales | DECIMAL | Чистые продажи |
| M | BaseCommission | DECIMAL | Базовая комиссия |
| N | DynamicCommission | DECIMAL | Динамическая комиссия |
| O | BonusCommission | DECIMAL | Бонусная комиссия |
| P | TotalCommissions | DECIMAL | Всего комиссий |
| Q | TotalEarnings | DECIMAL | Итого заработок |
| R | CreatedAt | DATETIME | Дата создания |

---

## Sync Processors

### Маппинг PostgreSQL → Google Sheets

| PostgreSQL Table | Google Sheet | Processor | Приоритет |
|-----------------|--------------|-----------|-----------|
| shifts | Shifts | ShiftSyncProcessor | 1 |
| active_bonuses | ActiveBonuses | BonusSyncProcessor | 2 |
| employee_ranks | EmployeeRanks | RankSyncProcessor | 3 |
| employees | EmployeeSettings | EmployeeSyncProcessor | 4 |
| employee_fortnights | EmployeeFortnights | FortnightSyncProcessor | 5 |

### Особенности

**RankSyncProcessor** - использует composite key (employee_id, year, month) вместо простого ID для поиска строк.

**ShiftSyncProcessor** - собирает данные из shift_products для колонок ModelA-ModelD.

**FortnightSyncProcessor** - 18 колонок с разбивкой комиссий на base/dynamic/bonus.

---

## Система рангов

### Ранги (по порядку)

| Ранг | Min Sales | Max Sales | Бонусы |
|------|-----------|-----------|--------|
| Rookie | $0 | $4,000 | - |
| Hustler | $4,000 | $8,000 | flat_10 |
| Closer | $8,000 | $15,000 | percent_next_1 |
| Shark | $15,000 | $25,000 | percent_all_2 |
| King of Greed | $25,000 | $50,000 | double_commission |
| Chatting God | $50,000 | ∞ | flat_100 |

### Типы бонусов

| Тип | Описание |
|-----|----------|
| `flat_X` | Единоразовый бонус $X |
| `percent_next_X` | +X% к следующей смене |
| `percent_all_X` | +X% ко всем сменам месяца |
| `percent_prev_X` | +X% к предыдущей смене |
| `double_commission` | Удвоение комиссии |
| `flat_immediate_X` | Немедленный бонус $X |

---

## Админские команды

### /recalc_ranks

Пересчёт рангов всех сотрудников за текущий месяц.

**Доступ:** только ADMIN_IDS
```python
ADMIN_IDS = [7867347055, 2125295046, 8152358885, 7367062056]
```

**Действия:**
1. Получить всех сотрудников с активностью за месяц
2. Пересчитать total_sales из shifts
3. Определить новый ранг
4. Сравнить с предыдущим
5. Начислить бонусы при повышении
6. Отправить отчёт админу

---

## Технический стек

| Компонент | Технология |
|-----------|------------|
| Runtime | Python 3.12 |
| Bot Framework | python-telegram-bot |
| Database | PostgreSQL |
| DB Driver | psycopg2 |
| Google Sheets | gspread |
| Process Manager | systemd |
| Timezone | America/New_York (ET) |

---

## Файловая структура

```
/opt/alex12060-bot/
├── bot.py                      # Entry point
├── config.py                   # Configuration
├── pg_sync_worker.py           # Sync daemon
├── src/
│   ├── handlers/               # Telegram handlers
│   ├── keyboards.py            # Inline keyboards
│   └── time_utils.py           # Time utilities
├── services/
│   ├── postgres_service.py     # Main DB service
│   ├── rank_service.py         # Rank logic
│   ├── cache_manager.py        # Caching
│   ├── singleton.py            # Service instances
│   └── sync/                   # Sync processors
│       ├── base_processor.py
│       ├── shift_processor.py
│       ├── bonus_processor.py
│       ├── rank_processor.py
│       ├── employee_processor.py
│       └── fortnight_processor.py
├── database/                   # Schema & migrations
├── logs/                       # Log files
├── venv/                       # Virtual environment
└── .env                        # Environment variables
```

---

## Переменные окружения

```env
# Telegram
TELEGRAM_BOT_TOKEN=...

# PostgreSQL
DB_HOST=localhost
DB_NAME=alex12060
DB_USER=alex12060_user
DB_PASSWORD=alex12060_pass

# Google Sheets
SPREADSHEET_ID=...
```

---

## Systemd сервисы

### alex12060-bot
- Основной Telegram бот
- Restart: always

### alex12060-sync-worker
- Синхронизация PostgreSQL → Google Sheets
- Интервал: 5 минут
- Restart: always

---

**Версия:** 4.0.0
**Последнее обновление:** 2025-12-19
