#!/usr/bin/env python3
"""Demo script to show the new shift message format."""

from handlers import format_shift_details

# Mock shift data as it would come from Google Sheets
mock_shift_data = {
    "ID": "123",
    "Date": "2025/11/10",
    "Clock in": "2025/11/10 09:00:00",
    "Clock out": "2025/11/10 17:00:00",
    "Worked hours/shift": "8.0",
    "Bella": "100.50",
    "Laura": "75.25",
    "Sophie": "50.00",
    "Alice": "0",
    "Emma": "0",
    "Molly": "0",
    "Other": "24.25",
    "Total sales": "250.00",
    "Net sales": "200.00",
    "%": "15.0",
    "Total per hour": "25.00",
    "Commissions": "30.00",
    "Total made": "230.00",
}

# Mock employee ID
employee_id = 1
shift_id = 123

print("=" * 70)
print("ДЕМОНСТРАЦИЯ НОВОГО ФОРМАТА СООБЩЕНИЯ ПРИ РЕДАКТИРОВАНИИ СМЕНЫ")
print("=" * 70)
print()

try:
    # Format the shift details
    shift_message = format_shift_details(mock_shift_data, employee_id, shift_id)

    print(shift_message)
    print()
    print("=" * 70)
    print("Обратите внимание:")
    print("1. ✅ Показывается полная информация о смене (время, продукты, итоги)")
    print("2. ✅ Commission % показывается с breakdown (base + dynamic + bonus)")
    print("3. ✅ Формат соответствует сообщению при создании смены")
    print("=" * 70)

except Exception as e:
    print(f"❌ Ошибка: {e}")
    import traceback
    traceback.print_exc()
