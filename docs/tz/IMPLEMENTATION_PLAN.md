# План реализации Commission Rework

**Дата:** 2025-12-12
**Версия:** 1.0
**Статус:** Draft

---

## 1. Обзор изменений

### 1.1 Что меняется

| Компонент | Было | Станет |
|-----------|------|--------|
| Base commission | Фиксированная 8% в `employees.sales_commission` | Tier A/B/C (4-6%) по продажам прошлого месяца |
| Dynamic rate | 0-3% по продажам смены | **Удаляется** |
| Rolling average | Нет | Взвешенное среднее за 7 дней |
| Bonus counter | Нет | Boolean: total_sales >= rolling_average |
| Fortnights | Нет | История выплат по периодам |
| total_per_hour | Название поля | Переименовать в `total_hourly` |

### 1.2 Новые таблицы

- `base_commissions` — тиры комиссий (вместо `dynamic_rates`)
- `employee_fortnights` — история выплат по периодам
- `bonus_settings` — настройки bonus_counter_percentage

### 1.3 Изменяемые таблицы

- `employees` — sales_commission становится FK
- `shifts` — новые поля rolling_average, bonus_counter; переименование total_per_hour

---

## 2. Изменения в БД

### 2.1 Новая таблица `base_commissions`

```sql
CREATE TABLE base_commissions (
    id SERIAL PRIMARY KEY,
    name VARCHAR(50) NOT NULL,              -- 'Tier A', 'Tier B', 'Tier C'
    min_amount DECIMAL(12,2) NOT NULL,      -- Минимум total_sales за месяц
    max_amount DECIMAL(12,2) NOT NULL,      -- Максимум total_sales за месяц
    percentage DECIMAL(5,2) NOT NULL,       -- Процент комиссии
    is_active BOOLEAN DEFAULT TRUE,
    display_order INT DEFAULT 0,
    created_at TIMESTAMP DEFAULT now(),
    updated_at TIMESTAMP DEFAULT now()
);

-- Начальные данные
INSERT INTO base_commissions (name, min_amount, max_amount, percentage, display_order) VALUES
('Tier A', 100000, 300000, 4.0, 1),
('Tier B', 50000, 99999.99, 5.0, 2),
('Tier C', 0, 49999.99, 6.0, 3);
```

### 2.2 Новая таблица `employee_fortnights`

```sql
CREATE TABLE employee_fortnights (
    id SERIAL PRIMARY KEY,
    employee_id BIGINT NOT NULL REFERENCES employees(id),
    year INT NOT NULL,
    month INT NOT NULL,                     -- 1-12
    fortnight INT NOT NULL,                 -- 1 или 2

    -- Агрегированные данные за период
    total_shifts INT DEFAULT 0,             -- Кол-во смен
    total_worked_hours DECIMAL(10,2) DEFAULT 0,
    total_sales DECIMAL(12,2) DEFAULT 0,
    total_commissions DECIMAL(10,2) DEFAULT 0,
    total_hourly_pay DECIMAL(10,2) DEFAULT 0,  -- sum(total_hourly)
    total_made DECIMAL(10,2) DEFAULT 0,     -- sum(total_made) за период

    -- Bonus counter
    bonus_counter_true_count INT DEFAULT 0, -- Кол-во смен с bonus_counter=true
    bonus_amount DECIMAL(10,2) DEFAULT 0,   -- bonus_count * total_commissions * 0.01

    -- Итого к выплате
    total_salary DECIMAL(10,2) DEFAULT 0,   -- total_made + bonus_amount

    -- Метаданные
    payment_date DATE,                      -- Дата выплаты (16-е или 1-е)
    is_paid BOOLEAN DEFAULT FALSE,
    synced_to_sheets BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT now(),
    updated_at TIMESTAMP DEFAULT now(),

    UNIQUE (employee_id, year, month, fortnight)
);

CREATE INDEX idx_employee_fortnights_employee ON employee_fortnights(employee_id);
CREATE INDEX idx_employee_fortnights_period ON employee_fortnights(year, month, fortnight);
```

### 2.3 Новая таблица `bonus_settings`

```sql
CREATE TABLE bonus_settings (
    id SERIAL PRIMARY KEY,
    setting_key VARCHAR(50) UNIQUE NOT NULL,
    setting_value DECIMAL(10,4) NOT NULL,
    description TEXT,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT now(),
    updated_at TIMESTAMP DEFAULT now()
);

INSERT INTO bonus_settings (setting_key, setting_value, description) VALUES
('bonus_counter_percentage', 0.01, 'Процент бонуса за bonus_counter=true (1%)');
```

### 2.4 Изменения в `employees`

```sql
-- Добавить новые поля
ALTER TABLE employees
ADD COLUMN base_commission_id INT REFERENCES base_commissions(id),
ADD COLUMN last_tier_update DATE;  -- Когда последний раз обновлялся tier

-- Миграция данных: всем назначить Tier C (id=3) по умолчанию
UPDATE employees SET base_commission_id = 3 WHERE base_commission_id IS NULL;

-- Опционально: сделать NOT NULL после миграции
-- ALTER TABLE employees ALTER COLUMN base_commission_id SET NOT NULL;

-- Старое поле sales_commission оставить для обратной совместимости
-- или удалить после полной миграции
```

### 2.5 Изменения в `shifts`

```sql
-- Переименовать поле
ALTER TABLE shifts RENAME COLUMN total_per_hour TO total_hourly;

-- Добавить новые поля
ALTER TABLE shifts
ADD COLUMN rolling_average DECIMAL(12,2),
ADD COLUMN bonus_counter BOOLEAN DEFAULT FALSE;

-- Индекс для быстрого подсчёта bonus_counter
CREATE INDEX idx_shifts_bonus_counter ON shifts(employee_id, date, bonus_counter);
```

### 2.6 Удаление/деактивация `dynamic_rates`

```sql
-- Вариант 1: Деактивировать (безопасно)
UPDATE dynamic_rates SET is_active = FALSE;

-- Вариант 2: Удалить таблицу (после полной миграции)
-- DROP TABLE dynamic_rates;
```

### 2.7 Триггеры для sync_queue

```sql
-- Триггер для employee_fortnights
CREATE OR REPLACE FUNCTION trigger_sync_employee_fortnights()
RETURNS TRIGGER AS $$
BEGIN
    INSERT INTO sync_queue (table_name, record_id, operation, data, priority)
    VALUES (
        'employee_fortnights',
        COALESCE(NEW.id, OLD.id),
        TG_OP,
        CASE
            WHEN TG_OP = 'DELETE' THEN to_jsonb(OLD)
            ELSE to_jsonb(NEW)
        END,
        2
    );
    RETURN COALESCE(NEW, OLD);
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER sync_employee_fortnights
AFTER INSERT OR UPDATE OR DELETE ON employee_fortnights
FOR EACH ROW EXECUTE FUNCTION trigger_sync_employee_fortnights();
```

---

## 3. Изменения в коде

### 3.1 Файлы для изменения

| Файл | Изменения |
|------|-----------|
| `services/postgres_service.py` | Основная логика: tier calculation, rolling_average, bonus_counter, fortnights |
| `src/handlers.py` | Обновить отображение комиссий, добавить bonus_counter в UI |
| `pg_sync_worker.py` | Добавить синхронизацию employee_fortnights |
| `config.py` | Добавить константы для fortnight периодов |

### 3.2 PostgresService — новые методы

```python
# === Base Commissions (Tiers) ===

def get_base_commissions(self) -> List[Dict]:
    """Получить все тиры комиссий."""
    pass

def get_employee_tier(self, employee_id: int) -> Dict:
    """Получить текущий tier сотрудника."""
    pass

def calculate_employee_tier(self, employee_id: int, year: int, month: int) -> int:
    """
    Рассчитать tier по продажам ПРОШЛОГО месяца.
    Возвращает base_commission_id.
    """
    pass

def update_employee_tier(self, employee_id: int) -> Dict:
    """
    Обновить tier сотрудника на основе продаж прошлого месяца.
    Вызывается в начале месяца или при создании смены.
    """
    pass


# === Rolling Average ===

def calculate_rolling_average(self, employee_id: int, shift_date: date) -> Optional[Decimal]:
    """
    Рассчитать взвешенное среднее за последние 7 календарных дней.

    Формула: Σ(weight_i × sales_i) / Σ(weights)
    где weight = порядковый номер дня (1 = самый старый, N = самый свежий)

    Returns:
        Decimal если есть смены, None если нет смен за 7 дней
    """
    pass

def calculate_bonus_counter(self, total_sales: Decimal, rolling_average: Optional[Decimal]) -> bool:
    """
    Определить bonus_counter.

    Returns:
        True если total_sales >= rolling_average
        False если rolling_average is None или total_sales < rolling_average
    """
    pass


# === Fortnights ===

def get_fortnight_number(self, day: int) -> int:
    """Определить номер fortnight по дню месяца (1-15 → 1, 16-31 → 2)."""
    return 1 if day <= 15 else 2

def get_fortnight_payment_date(self, year: int, month: int, fortnight: int) -> date:
    """
    Получить дату выплаты для fortnight.
    F1 (1-15) → 16-е текущего месяца
    F2 (16-31) → 1-е следующего месяца
    """
    pass

def get_or_create_fortnight(self, employee_id: int, year: int, month: int, fortnight: int) -> Dict:
    """Получить или создать запись fortnight."""
    pass

def update_fortnight_totals(self, employee_id: int, year: int, month: int, fortnight: int):
    """
    Пересчитать агрегаты fortnight из shifts.
    Вызывается после создания/редактирования смены.
    """
    pass

def calculate_fortnight_bonus(self, employee_id: int, year: int, month: int, fortnight: int) -> Decimal:
    """
    Рассчитать bonus_amount = bonus_counter_true_count × total_commissions × 0.01
    """
    pass

def get_employee_fortnights(self, employee_id: int, year: int = None, month: int = None) -> List[Dict]:
    """Получить историю fortnights сотрудника."""
    pass
```

### 3.3 PostgresService — изменения в create_shift()

```python
def create_shift(self, shift_data: dict) -> int:
    # ... существующая логика ...

    # 1. Проверить/обновить tier сотрудника (если начало месяца)
    self._check_and_update_tier(employee_id, shift_date)

    # 2. Получить base_commission из tier (вместо employees.sales_commission)
    tier = self.get_employee_tier(employee_id)
    base_commission = Decimal(str(tier['percentage']))

    # 3. Dynamic rate УДАЛЁН — commission_pct = base_commission + bonuses
    commission_pct = base_commission
    # ... применение active_bonuses ...

    # 4. Рассчитать rolling_average
    rolling_average = self.calculate_rolling_average(employee_id, shift_date)

    # 5. Определить bonus_counter
    bonus_counter = self.calculate_bonus_counter(total_sales, rolling_average)

    # 6. INSERT с новыми полями
    cursor.execute("""
        INSERT INTO shifts (..., rolling_average, bonus_counter, total_hourly, ...)
        VALUES (..., %s, %s, %s, ...)
    """, (..., rolling_average, bonus_counter, total_hourly, ...))

    # 7. Обновить fortnight агрегаты
    fortnight_num = self.get_fortnight_number(shift_date.day)
    self.update_fortnight_totals(employee_id, shift_date.year, shift_date.month, fortnight_num)

    return shift_id
```

### 3.4 Handlers — обновление UI

```python
def get_commission_breakdown(employee_id, commission_pct, shift_id=None) -> str:
    """
    Новый формат:
    "Tier C: 6.0% base + 2.0% bonus = 8.00%"
    """
    tier = sheets.get_employee_tier(employee_id)
    tier_name = tier['name']  # "Tier A", "Tier B", "Tier C"
    base = tier['percentage']

    # ... логика бонусов ...

    return f"{tier_name}: {base}% base + {bonus}% bonus = {total}%"

def format_shift_details(shift) -> str:
    """
    Добавить отображение rolling_average и bonus_counter.
    """
    # ... существующее форматирование ...

    rolling_avg = shift.get('rolling_average')
    bonus_counter = shift.get('bonus_counter', False)

    if rolling_avg is not None:
        text += f"\n📊 Rolling Avg: ${rolling_avg:,.2f}"
        text += f"\n{'✅' if bonus_counter else '❌'} Bonus Counter: {bonus_counter}"

    return text
```

### 3.5 pg_sync_worker.py — синхронизация fortnights

```python
def _sync_employee_fortnight(self, record: dict) -> bool:
    """Синхронизация employee_fortnights → Google Sheets."""

    # Лист: EmployeeFortnights
    # Колонки: ID, EmployeeID, Year, Month, Fortnight, TotalShifts,
    #          TotalSales, TotalCommissions, TotalMade, BonusCount,
    #          BonusAmount, TotalSalary, PaymentDate, IsPaid
    pass
```

---

## 4. Миграция данных

### 4.1 Порядок миграции

1. **Создать новые таблицы** (base_commissions, employee_fortnights, bonus_settings)
2. **Изменить существующие таблицы** (employees, shifts)
3. **Заполнить base_commissions** начальными данными
4. **Назначить всем сотрудникам Tier C** по умолчанию
5. **Рассчитать tier для активных сотрудников** по продажам прошлого месяца
6. **Пересчитать rolling_average и bonus_counter** для существующих смен (опционально)
7. **Создать fortnight записи** для существующих смен (опционально)

### 4.2 SQL миграции

```sql
-- Файл: migrations/001_create_base_commissions.sql
-- Файл: migrations/002_create_employee_fortnights.sql
-- Файл: migrations/003_create_bonus_settings.sql
-- Файл: migrations/004_alter_employees.sql
-- Файл: migrations/005_alter_shifts.sql
-- Файл: migrations/006_migrate_tiers.sql
-- Файл: migrations/007_create_triggers.sql
```

---

## 5. Тестирование

### 5.1 Unit тесты

- [ ] `test_calculate_rolling_average()` — разные сценарии (7 дней, <7 дней, 0 дней)
- [ ] `test_calculate_bonus_counter()` — граничные случаи
- [ ] `test_calculate_employee_tier()` — все тиры
- [ ] `test_fortnight_calculations()` — агрегация и бонусы

### 5.2 Integration тесты

- [ ] Создание смены с новой логикой
- [ ] Обновление tier в начале месяца
- [ ] Синхронизация fortnights в Google Sheets

### 5.3 Ручное тестирование

- [ ] Создать смену, проверить rolling_average и bonus_counter
- [ ] Проверить расчёт fortnight total_salary
- [ ] Проверить синхронизацию в Google Sheets

---

## 6. План выполнения

### Этап 1: База данных (1-2 часа)
1. Создать SQL миграции
2. Применить на DEV (Pi4-2)
3. Проверить структуру

### Этап 2: Backend логика (2-3 часа)
1. Реализовать методы в postgres_service.py
2. Обновить create_shift()
3. Обновить update методы

### Этап 3: UI/Handlers (1 час)
1. Обновить отображение комиссий
2. Добавить bonus_counter в сообщения

### Этап 4: Синхронизация (1 час)
1. Добавить sync для employee_fortnights
2. Обновить sync для shifts (новые поля)

### Этап 5: Тестирование (1-2 часа)
1. Тесты на DEV
2. Фикс багов

### Этап 6: Деплой на PROD
1. Бэкап БД
2. Применить миграции
3. Деплой кода
4. Мониторинг

---

## 7. Риски и митигация

| Риск | Вероятность | Митигация |
|------|-------------|-----------|
| Ошибка в расчёте rolling_average | Средняя | Unit тесты, сверка с Excel |
| Потеря данных при миграции | Низкая | Бэкап перед миграцией |
| Несовместимость с Google Sheets | Низкая | Тест синхронизации на DEV |
| Неправильный tier у сотрудников | Средняя | Ручная проверка после миграции |

---

## 8. Откат

В случае критических проблем:

1. Восстановить БД из бэкапа
2. Откатить код через `git revert`
3. Перезапустить сервисы

---

## Приложение A: Формулы

### Rolling Average
```
weights = [1, 2, 3, ..., N]  где N = кол-во смен за 7 дней
rolling_average = Σ(weight_i × sales_i) / Σ(weights)
```

### Bonus Counter
```
bonus_counter = (rolling_average IS NOT NULL) AND (total_sales >= rolling_average)
```

### Fortnight Total Salary
```
bonus_amount = bonus_counter_true_count × total_commissions × 0.01
total_salary = total_made + bonus_amount
```

### Tier Determination
```
tier = SELECT * FROM base_commissions
       WHERE prev_month_sales BETWEEN min_amount AND max_amount
```
