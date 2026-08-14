from datetime import datetime
from decimal import Decimal

from app.data.repositories.audit_ledger import AuditLedger
from app.data.repositories.rules_repository import RulesRepository


class MonthlyLogService:
    def __init__(
        self,
        ledger: AuditLedger,
        rules_repository: RulesRepository | None = None,
    ) -> None:
        self.ledger = ledger
        self.cards = (rules_repository or RulesRepository()).cards()

    def get_month(self, year: int, month: int) -> dict:
        transactions = self.ledger.monthly_transactions(year, month)
        return {"year": year, "month": month, "totals": self._totals(transactions), "transactions": transactions}

    def get_all_transactions(self) -> list[dict]:
        return self.ledger.read_transactions()

    def delete_transaction(self, transaction_id: str) -> bool:
        return self.ledger.delete_transaction(transaction_id)

    def get_summary(self) -> dict:
        now = datetime.now()
        transactions = self.ledger.read_transactions()
        month_rows = [
            row for row in transactions
            if datetime.fromisoformat(row["paid_at"]).year == now.year
            and datetime.fromisoformat(row["paid_at"]).month == now.month
        ]
        year_rows = [
            row for row in transactions
            if datetime.fromisoformat(row["paid_at"]).year == now.year
        ]
        return {
            "month": self._totals(month_rows),
            "year_to_date": self._totals(year_rows),
            "cards": self._card_totals(month_rows),
        }

    def _totals(self, transactions: list[dict]) -> dict:
        totals = {
            "transaction_count": len(transactions),
            "final_amount_paid": sum(float(row["final_amount_paid"]) for row in transactions),
            "total_points": sum(float(row["total_points"]) for row in transactions),
            "bonus_points": sum(float(row["bonus_points"]) for row in transactions),
            "points_value_rupees": sum(float(row["points_value_rupees"]) for row in transactions),
            "net_cost": sum(float(row["net_cost"]) for row in transactions),
        }
        return totals

    def _card_totals(self, transactions: list[dict]) -> list[dict]:
        rows = []
        for card in self.cards:
            card_rows = [row for row in transactions if row["card_id"] == card.id]
            bonus_points = sum(Decimal(row["bonus_points"]) for row in card_rows)
            rows.append(
                {
                    "card_id": card.id,
                    "card_name": card.name,
                    "total_points": str(sum(Decimal(row["total_points"]) for row in card_rows)),
                    "bonus_points": str(bonus_points),
                    "bonus_points_remaining": str(max(card.cycle_bonus_cap - bonus_points, Decimal("0"))),
                    "cycle_bonus_cap": str(card.cycle_bonus_cap),
                }
            )
        return rows
