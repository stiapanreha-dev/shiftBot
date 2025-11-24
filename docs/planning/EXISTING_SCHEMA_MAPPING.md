# Existing PostgreSQL Schema Mapping

**Date:** 2025-11-11
**Purpose:** Mapping between expected schema and actual existing schema

---

## Tables and Column Mapping

### 1. shifts

**Existing columns:**
- `id` (PK, serial)
- `date` (timestamp)
- `employee_id` (integer, FK to employees)
- `employee_name` (varchar)
- `clock_in` (timestamp)
- `clock_out` (timestamp)
- `worked_hours` (numeric(5,2))
- `total_sales` (numeric(10,2))
- `net_sales` (numeric(10,2))
- `commission_pct` (numeric(5,2))
- `total_per_hour` (numeric(10,2))
- `commissions` (numeric(10,2))
- `total_made` (numeric(10,2))
- `created_at` (timestamp)
- `updated_at` (timestamp)
- `synced_to_sheets` (boolean)
- `sheets_sync_at` (timestamp)

**Mapping to SheetsService interface:**
- `id` → `shift_id`
- `date` → `shift_date`
- `clock_in` → parse to `time_in`
- `clock_out` → parse to `time_out`
- `commission_pct` → `total_commission_pct`
- `commissions` → `commission_amount`

**Product sales:** Stored in separate `shift_products` table

---

### 2. employees

**Existing columns:**
- `id` (PK, serial)
- `name` (varchar, unique)
- `telegram_id` (bigint, unique)
- `is_active` (boolean)
- `created_at` (timestamp)
- `updated_at` (timestamp)

**Mapping to SheetsService interface (employee_settings):**
- `id` → `employee_id`
- `name` → `employee_name`
- `is_active` → `active`
- **Missing:** `base_commission_pct` (needs default value or separate table)

---

### 3. products

**Existing columns:**
- `id` (PK, serial)
- `name` (varchar, unique)
- `display_order` (integer)
- `is_active` (boolean)
- `created_at` (timestamp)

**Expected products:** Bella, Laura, Sophie, Alice, Emma, Molly

---

### 4. shift_products

**Existing columns:**
- `id` (PK, serial)
- `shift_id` (FK to shifts, with unique constraint)
- `product_id` (FK to products)
- `amount` (numeric(10,2))

**Purpose:** Normalized many-to-many between shifts and products

---

### 5. dynamic_rates

**Existing columns:**
- `id` (PK, serial)
- `min_amount` (numeric(10,2)) ← **NOT** min_sales
- `max_amount` (numeric(10,2)) ← **NOT** max_sales
- `percentage` (numeric(5,2)) ← **NOT** rate_pct
- `is_active` (boolean)
- `created_at` (timestamp)
- `updated_at` (timestamp)

**Mapping:**
- `min_amount` → `min_sales`
- `max_amount` → `max_sales`
- `percentage` → `rate_pct`

---

### 6. ranks

**Existing columns:**
- Need to check structure

---

### 7. employee_ranks

**Existing columns:**
- `id` (PK, serial)
- `employee_id` (FK to employees)
- `month` (varchar) - Format: YYYY-MM
- `rank_id` (FK to ranks)
- `created_at` (timestamp)

---

### 8. active_bonuses

**Existing columns:**
- Need to check structure

---

### 9. sync_queue

**Purpose:** Queue for syncing changes to Google Sheets

**Columns:**
- `id` (PK, serial)
- `table_name` (varchar)
- `record_id` (integer)
- `operation` (varchar)
- `created_at` (timestamp)
- `processed_at` (timestamp)

---

## Database Functions

### 1. `get_dynamic_rate(sales_amount numeric) → numeric`
Calculate dynamic rate based on sales amount.

### 2. `get_employee_rank(emp_id integer, year_val integer, month_val integer) → varchar`
Get employee rank for specific month.

### 3. `get_employee_daily_total_before(emp_id integer, shift_date date, shift_id_exclude integer) → numeric`
Get total sales for employee before specific shift on same day.

### 4. `calculate_shift_total(shift_id_param integer) → numeric`
Calculate total for a shift including products.

### 5. `add_to_sync_queue()` (trigger function)
Adds record to sync_queue when shifts are modified.

### 6. `refresh_employee_daily_sales()` (trigger function)
Refreshes daily sales materialized view.

### 7. `refresh_employee_monthly_sales()` (trigger function)
Refreshes monthly sales materialized view.

---

## Key Differences from Expected Schema

1. **Normalized structure**: Products in separate table, not as columns in shifts
2. **Different column names**: `min_amount` vs `min_sales`, `percentage` vs `rate_pct`
3. **Additional features**: Sync queue, materialized views, database functions
4. **User ownership**: `alex12060_user` owns tables, not `lexun`

---

## Next Steps

1. Update `postgres_service_adapted.py` with correct column names
2. Add support for shift_products table
3. Test all methods with actual schema
4. Consider using database functions instead of application logic where possible

---

**Status:** Schema analyzed, needs code adaptation
