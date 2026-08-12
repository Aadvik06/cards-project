import json
from dataclasses import asdict, is_dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from app.domain.models import DecisionRecord, TransactionRecord


class AuditLedger:
    def __init__(self, root: Path | str = "data/runtime") -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.decisions_path = self.root / "decisions.jsonl"
        self.transactions_path = self.root / "transactions.jsonl"

    def append_decision(self, decision: DecisionRecord) -> None:
        self._append_jsonl(self.decisions_path, decision)

    def append_transaction(self, transaction: TransactionRecord) -> None:
        self._append_jsonl(self.transactions_path, transaction)

    def read_decisions(self) -> list[dict[str, Any]]:
        return self._read_jsonl(self.decisions_path)

    def read_transactions(self) -> list[dict[str, Any]]:
        return self._read_jsonl(self.transactions_path)

    def monthly_transactions(self, year: int, month: int) -> list[dict[str, Any]]:
        rows = []
        for row in self.read_transactions():
            paid_at = datetime.fromisoformat(row["paid_at"])
            if paid_at.year == year and paid_at.month == month:
                rows.append(row)
        return rows

    def _append_jsonl(self, path: Path, value: Any) -> None:
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(self._to_json(value), sort_keys=True) + "\n")

    def _read_jsonl(self, path: Path) -> list[dict[str, Any]]:
        if not path.exists():
            return []
        with path.open("r", encoding="utf-8") as handle:
            return [json.loads(line) for line in handle if line.strip()]

    def _to_json(self, value: Any) -> Any:
        if is_dataclass(value):
            return self._to_json(asdict(value))
        if isinstance(value, dict):
            return {key: self._to_json(item) for key, item in value.items()}
        if isinstance(value, list):
            return [self._to_json(item) for item in value]
        if isinstance(value, Decimal):
            return str(value)
        if isinstance(value, datetime):
            return value.isoformat()
        if hasattr(value, "value"):
            return value.value
        return value

