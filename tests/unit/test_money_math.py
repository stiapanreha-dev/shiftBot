"""Unit tests for the money math: commissions, rolling average, fortnights, bonus counter."""

from datetime import date
from decimal import Decimal

from services.calculators import CommissionCalculator
from services.mixins.rolling_mixin import RollingMixin
from services.mixins.fortnight_mixin import FortnightMixin


class TestCommissionCalculator:
    """CommissionCalculator.calculate — the single source of truth."""

    def setup_method(self):
        self.calc = CommissionCalculator()

    def test_basic_no_bonuses(self):
        result = self.calc.calculate(
            total_sales=Decimal('1000'),
            worked_hours=Decimal('8'),
            hourly_wage=Decimal('15'),
            base_commission_pct=Decimal('8'),
        )
        # net = 1000 * 0.8 = 800; commissions = 800 * 8% = 64; hourly = 120
        assert result.commissions == Decimal('64.0')
        assert result.total_made == Decimal('184.0')
        assert result.commission_pct == Decimal('8')
        assert result.applied_bonus_ids == []

    def test_default_base_commission(self):
        result = self.calc.calculate(
            total_sales=Decimal('100'),
            worked_hours=Decimal('0'),
            hourly_wage=Decimal('15'),
        )
        assert result.commission_pct == CommissionCalculator.DEFAULT_BASE_COMMISSION

    def test_percent_next_bonus(self):
        bonuses = [{'ID': 7, 'Bonus Type': 'percent_next', 'Value': 2}]
        result = self.calc.calculate(
            total_sales=Decimal('1000'),
            worked_hours=Decimal('8'),
            hourly_wage=Decimal('15'),
            base_commission_pct=Decimal('8'),
            active_bonuses=bonuses,
        )
        assert result.commission_pct == Decimal('10')
        assert result.bonus_pct == Decimal('2')
        assert result.commissions == Decimal('80.0')  # 800 * 10%
        assert result.applied_bonus_ids == [7]

    def test_double_commission_bonus(self):
        bonuses = [{'ID': 3, 'Bonus Type': 'double_commission', 'Value': 0}]
        result = self.calc.calculate(
            total_sales=Decimal('1000'),
            worked_hours=Decimal('0'),
            hourly_wage=Decimal('15'),
            base_commission_pct=Decimal('8'),
            active_bonuses=bonuses,
        )
        assert result.commission_pct == Decimal('16')
        assert result.commissions == Decimal('128.0')
        assert result.applied_bonus_ids == [3]

    def test_flat_bonus_added_to_total_only(self):
        bonuses = [{'ID': 5, 'Bonus Type': 'flat', 'Value': 50}]
        result = self.calc.calculate(
            total_sales=Decimal('1000'),
            worked_hours=Decimal('8'),
            hourly_wage=Decimal('15'),
            base_commission_pct=Decimal('8'),
            active_bonuses=bonuses,
        )
        assert result.commissions == Decimal('64.0')  # unchanged
        assert result.flat_bonuses == Decimal('50')
        assert result.total_made == Decimal('234.0')  # 64 + 120 + 50

    def test_apply_bonuses_false_ignores_bonuses(self):
        bonuses = [{'ID': 7, 'Bonus Type': 'percent_next', 'Value': 2}]
        result = self.calc.calculate(
            total_sales=Decimal('1000'),
            worked_hours=Decimal('8'),
            hourly_wage=Decimal('15'),
            base_commission_pct=Decimal('8'),
            active_bonuses=bonuses,
            apply_bonuses=False,
        )
        assert result.commission_pct == Decimal('8')
        assert result.applied_bonus_ids == []

    def test_recalculate_from_existing_keeps_pct(self):
        result = self.calc.recalculate_from_existing(
            total_sales=Decimal('500'),
            worked_hours=Decimal('4'),
            hourly_wage=Decimal('15'),
            existing_commission_pct=Decimal('10'),
        )
        # net = 400; commissions = 40; hourly = 60
        assert result.commission_pct == Decimal('10')
        assert result.commissions == Decimal('40.0')
        assert result.total_made == Decimal('100.0')
        assert result.applied_bonus_ids == []

    def test_net_sales_ratio(self):
        assert CommissionCalculator.calculate_net_sales(Decimal('100')) == Decimal('80.0')


class TestRollingAverage:
    """Weighted rolling average formula (last 7 shifts)."""

    def test_empty_returns_zero(self):
        assert RollingMixin.weighted_average([]) == Decimal('0')

    def test_single_shift(self):
        assert RollingMixin.weighted_average([Decimal('150')]) == Decimal('150.00')

    def test_documented_example(self):
        # CLAUDE.md example: [100, 200, 300] -> 1400 / 6 = 233.33
        sales = [Decimal('100'), Decimal('200'), Decimal('300')]
        assert RollingMixin.weighted_average(sales) == Decimal('233.33')

    def test_newest_weighs_most(self):
        ascending = RollingMixin.weighted_average([Decimal('0'), Decimal('600')])
        descending = RollingMixin.weighted_average([Decimal('600'), Decimal('0')])
        assert ascending == Decimal('400.00')  # (0*1 + 600*2) / 3
        assert descending == Decimal('200.00')  # (600*1 + 0*2) / 3

    def test_seven_equal_shifts(self):
        sales = [Decimal('100')] * 7
        assert RollingMixin.weighted_average(sales) == Decimal('100.00')

    def test_quantized_to_cents(self):
        result = RollingMixin.weighted_average([Decimal('100'), Decimal('101')])
        assert result == Decimal('100.67')  # 302 / 3 = 100.666...


class TestBonusCounter:
    """bonus_counter = total_sales >= rolling_average."""

    def setup_method(self):
        self.mixin = RollingMixin()

    def test_above_average(self):
        assert self.mixin.calculate_bonus_counter(Decimal('300'), Decimal('200')) is True

    def test_equal_counts(self):
        assert self.mixin.calculate_bonus_counter(Decimal('200'), Decimal('200')) is True

    def test_below_average(self):
        assert self.mixin.calculate_bonus_counter(Decimal('100'), Decimal('200')) is False

    def test_no_average_no_bonus(self):
        assert self.mixin.calculate_bonus_counter(Decimal('100'), None) is False


class TestFortnightBoundaries:
    """Fortnight number and payment dates."""

    def setup_method(self):
        self.mixin = FortnightMixin()

    def test_fortnight_number(self):
        assert self.mixin.get_fortnight_number(1) == 1
        assert self.mixin.get_fortnight_number(15) == 1
        assert self.mixin.get_fortnight_number(16) == 2
        assert self.mixin.get_fortnight_number(31) == 2

    def test_first_fortnight_paid_on_16th(self):
        assert self.mixin.get_fortnight_payment_date(2026, 6, 1) == date(2026, 6, 16)

    def test_second_fortnight_paid_next_month(self):
        assert self.mixin.get_fortnight_payment_date(2026, 6, 2) == date(2026, 7, 1)

    def test_december_second_fortnight_paid_in_january(self):
        assert self.mixin.get_fortnight_payment_date(2026, 12, 2) == date(2027, 1, 1)
