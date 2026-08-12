from datetime import date, datetime, timedelta
from decimal import Decimal

from app.data.repositories.audit_ledger import AuditLedger
from app.domain.enums import RefreshType
from app.domain.models import CreditCard, UsageSnapshot


class CapUsageService:
    def __init__(self, *, ledger: AuditLedger, cards: list[CreditCard]) -> None:
        self.ledger = ledger
        self.cards = {card.id: card for card in cards}

    def usage_for(self, target_date: date) -> dict[str, UsageSnapshot]:
        usage = {
            card_id: {
                "daily": Decimal("0"),
                "cycle": Decimal("0"),
            }
            for card_id in self.cards
        }

        for row in self.ledger.read_transactions():
            card = self.cards.get(row["card_id"])
            if card is None:
                continue
            paid_at = datetime.fromisoformat(row["paid_at"]).date()
            bonus_points = Decimal(row["bonus_points"])

            if paid_at == target_date:
                usage[card.id]["daily"] += bonus_points
            if self._in_same_cycle(card, paid_at, target_date):
                usage[card.id]["cycle"] += bonus_points

        return {
            card_id: UsageSnapshot(
                daily_bonus_points_used=values["daily"],
                cycle_bonus_points_used=values["cycle"],
            )
            for card_id, values in usage.items()
        }

    def _in_same_cycle(self, card: CreditCard, paid_at: date, target_date: date) -> bool:
        start, end = self._cycle_bounds(card, target_date)
        return start <= paid_at <= end

    def _cycle_bounds(self, card: CreditCard, target_date: date) -> tuple[date, date]:
        if card.refresh_type == RefreshType.CALENDAR_MONTH:
            start = target_date.replace(day=1)
            end = self._first_day_next_month(start) - timedelta(days=1)
            return start, end

        statement_day = card.statement_day or 1
        current_month_start = target_date.replace(day=min(statement_day, 28))
        if target_date < current_month_start:
            start = self._previous_month_same_day(current_month_start)
        else:
            start = current_month_start
        end = self._first_day_next_month(start) - timedelta(days=1)
        return start, end

    def _first_day_next_month(self, value: date) -> date:
        if value.month == 12:
            return value.replace(year=value.year + 1, month=1, day=1)
        return value.replace(month=value.month + 1, day=1)

    def _previous_month_same_day(self, value: date) -> date:
        if value.month == 1:
            return value.replace(year=value.year - 1, month=12)
        return value.replace(month=value.month - 1)

