from app.data.repositories.audit_ledger import AuditLedger


class MonthlyLogService:
    def __init__(self, ledger: AuditLedger) -> None:
        self.ledger = ledger

    def get_month(self, year: int, month: int) -> dict:
        transactions = self.ledger.monthly_transactions(year, month)
        totals = {
            "transaction_count": len(transactions),
            "final_amount_paid": sum(float(row["final_amount_paid"]) for row in transactions),
            "points_value_rupees": sum(float(row["points_value_rupees"]) for row in transactions),
            "net_cost": sum(float(row["net_cost"]) for row in transactions),
        }
        return {"year": year, "month": month, "totals": totals, "transactions": transactions}

