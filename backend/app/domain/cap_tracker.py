from decimal import Decimal

from app.core.decimal_math import non_negative
from app.domain.models import CreditCard, UsageSnapshot


def remaining_bonus_cap(card: CreditCard, usage: UsageSnapshot) -> Decimal:
    daily_remaining = non_negative(card.daily_bonus_cap - usage.daily_bonus_points_used)
    cycle_remaining = non_negative(card.cycle_bonus_cap - usage.cycle_bonus_points_used)
    return min(daily_remaining, cycle_remaining)

