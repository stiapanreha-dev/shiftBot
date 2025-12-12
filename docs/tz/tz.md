Необходимы следующие изменения
1) Уход от динамического бонуса, на самом деле надо переименовать данную таблицу в base_comissions, там будет отображаться информация по тирам сотрудников в зависимости от total sales за месяц, тир определяется диапазоном total sales, то есть:
Tier A - min_amount: 100 000, max amount: 300 000, percentage 4
Tier B - min_amount: 50 000, max_amount: 99 999, percentage 5
Tier C - min_amount: 0, max_amount: 49 999, percentage 6
Ввиду этого из таблицы employees необходимо будет изменить поле sales_commission, сделав его FK, который бы ссылался на id из таблицы base_commissions
2) Изменения в таблице shifts:
1. Из вышеописанного пункта следует, что commission_pct =  base_comissions.percentage сотрудника, формула commissions остается неизменной как и total_made
2. Добавить таблицу bonus_new с полем bonus_counter_percentage, ниже он будет упоминаться  
3. Необходимо добавить поля rolling average и bonus counter, rolling_average - это поле, которое должно подсчитывать среднее  total_sales с использованием последовательности чисел за предыдущие смены сотрудника за ПОСЛЕДНИЕ 7 дней, если быть более формальны то rolling_average = 1/28 (1 - первое число в последовательности, 28 = СУММ(от 1 до 7)) *  total_sales за первый день/СУММ(total sales за последние 7 дней) + 2/28 (28 = СУММ(от 1 до 7) *  total_sales за второй день/СУММ(total sales за последние 7 дней) итд.
bonus counter - это поле типа boolean, оно принимает значение true, если total sales за текущую смену >= rolling_average, в противном случае false. 
3. Переименовать поле total_per_hour в total_hourly
3) Необходимо добавить в таблицу employees поля month, year, fortnight и total_salary. fortnight - это период рабочих дней сотрудника, за которые ему будет производится выплата, всего их 2 в месяц, первый происходит 16-го числа (то есть  с 1-го по 15-ые календарные дни месяца) и второй 1-го числа следующего месяца (то есть с 16-го до последнего календарного дня месяца), total_salary = total_made + кол-во bonus_counter, где он равен true * commissions*bonus_counter_percentage (он будет равен 1%) ЗА Fortnight
Логика для таблицы shifts вам будет более понятна если взгляните на таблицу Commission_Rework.xlsx