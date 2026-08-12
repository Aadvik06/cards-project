from decimal import Decimal, ROUND_HALF_UP


MONEY_PLACES = Decimal("0.01")
POINT_PLACES = Decimal("0.0001")


def money(value: Decimal) -> Decimal:
    return value.quantize(MONEY_PLACES, rounding=ROUND_HALF_UP)


def points(value: Decimal) -> Decimal:
    return value.quantize(POINT_PLACES, rounding=ROUND_HALF_UP)


def non_negative(value: Decimal) -> Decimal:
    return max(value, Decimal("0"))

