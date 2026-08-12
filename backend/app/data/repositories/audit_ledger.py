import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterator

from app.domain.enums import TravelType
from app.domain.models import (
    DecisionRecord,
    QuoteInput,
    Recommendation,
    RecommendationOption,
    TransactionRecord,
)


class AuditLedger:
    def __init__(self, db_path: Path | str = "data/runtime/cards_project.sqlite3") -> None:
        self.db_path = Path(db_path)
        if self.db_path.exists() and self.db_path.is_dir():
            self.db_path = self.db_path / "cards_project.sqlite3"
        elif self.db_path.suffix == "":
            self.db_path = self.db_path / "cards_project.sqlite3"
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def save_recommendation(self, recommendation: Recommendation) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO recommendations (
                    id, employee_id, travel_type, quotes_json, created_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    recommendation.id,
                    recommendation.employee_id,
                    recommendation.travel_type.value,
                    json.dumps([self._quote_to_json(quote) for quote in recommendation.quotes]),
                    recommendation.created_at.isoformat(),
                ),
            )
            connection.execute(
                "DELETE FROM recommendation_options WHERE recommendation_id = ?",
                (recommendation.id,),
            )
            connection.executemany(
                """
                INSERT INTO recommendation_options (
                    id, recommendation_id, rank, card_id, card_name, vendor_id, vendor_name,
                    travel_type, listed_amount, eligible_amount, cash_component, discount_rate,
                    price_after_discount, base_points, raw_bonus_points, awarded_bonus_points,
                    capped_bonus_points, total_points, points_value_rupees, net_cost,
                    cap_remaining_after, explanation, card_rank
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    self._option_row(recommendation.id, option, self._card_rank(recommendation, option))
                    for option in recommendation.ranked_options
                ],
            )

    def get_recommendation(self, recommendation_id: str) -> Recommendation | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM recommendations WHERE id = ?",
                (recommendation_id,),
            ).fetchone()
            if row is None:
                return None

            option_rows = connection.execute(
                """
                SELECT * FROM recommendation_options
                WHERE recommendation_id = ?
                ORDER BY rank ASC
                """,
                (recommendation_id,),
            ).fetchall()

        ranked_options = [self._option_from_row(option_row, "rank") for option_row in option_rows]
        card_rankings = [
            self._option_from_row(option_row, "card_rank")
            for option_row in option_rows
            if option_row["card_rank"] is not None
        ]
        card_rankings.sort(key=lambda option: option.rank)

        return Recommendation(
            id=row["id"],
            employee_id=row["employee_id"],
            travel_type=TravelType(row["travel_type"]),
            quotes=[
                QuoteInput(
                    vendor_id=quote["vendor_id"],
                    amount=Decimal(quote["amount"]),
                    merchant_name=quote.get("merchant_name"),
                    description=quote.get("description"),
                    discount_rate=Decimal(quote["discount_rate"]),
                )
                for quote in json.loads(row["quotes_json"])
            ],
            ranked_options=ranked_options,
            card_rankings=card_rankings,
            created_at=datetime.fromisoformat(row["created_at"]),
        )

    def append_decision(self, decision: DecisionRecord) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO decisions (
                    recommendation_id, accepted, selected_option_id, selected_card_id,
                    selected_vendor_id, decline_reason, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    decision.recommendation_id,
                    int(decision.accepted),
                    decision.selected_option_id,
                    decision.selected_card_id,
                    decision.selected_vendor_id,
                    decision.decline_reason,
                    decision.created_at.isoformat(),
                ),
            )

    def append_transaction(self, transaction: TransactionRecord) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO transactions (
                    id, recommendation_id, employee_id, travel_type, card_id, vendor_id,
                    final_amount_paid, discount_rate, base_points, bonus_points, total_points,
                    points_value_rupees, net_cost, paid_at, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    transaction.id,
                    transaction.recommendation_id,
                    transaction.employee_id,
                    transaction.travel_type.value,
                    transaction.card_id,
                    transaction.vendor_id,
                    str(transaction.final_amount_paid),
                    str(transaction.discount_rate),
                    str(transaction.base_points),
                    str(transaction.bonus_points),
                    str(transaction.total_points),
                    str(transaction.points_value_rupees),
                    str(transaction.net_cost),
                    transaction.paid_at.isoformat(),
                    transaction.created_at.isoformat(),
                ),
            )

    def read_decisions(self) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM decisions ORDER BY created_at ASC"
            ).fetchall()
        return [self._dict(row) for row in rows]

    def get_decision(self, recommendation_id: str) -> DecisionRecord | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM decisions WHERE recommendation_id = ?",
                (recommendation_id,),
            ).fetchone()
        if row is None:
            return None
        return DecisionRecord(
            recommendation_id=row["recommendation_id"],
            accepted=bool(row["accepted"]),
            selected_option_id=row["selected_option_id"],
            selected_card_id=row["selected_card_id"],
            selected_vendor_id=row["selected_vendor_id"],
            decline_reason=row["decline_reason"],
            created_at=datetime.fromisoformat(row["created_at"]),
        )

    def read_transactions(self) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM transactions ORDER BY paid_at ASC"
            ).fetchall()
        return [self._dict(row) for row in rows]

    def monthly_transactions(self, year: int, month: int) -> list[dict[str, Any]]:
        rows = []
        for row in self.read_transactions():
            paid_at = datetime.fromisoformat(row["paid_at"])
            if paid_at.year == year and paid_at.month == month:
                rows.append(row)
        return rows

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS recommendations (
                    id TEXT PRIMARY KEY,
                    employee_id TEXT,
                    travel_type TEXT NOT NULL,
                    quotes_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS recommendation_options (
                    id TEXT PRIMARY KEY,
                    recommendation_id TEXT NOT NULL,
                    rank INTEGER NOT NULL,
                    card_id TEXT NOT NULL,
                    card_name TEXT NOT NULL,
                    vendor_id TEXT NOT NULL,
                    vendor_name TEXT NOT NULL,
                    travel_type TEXT NOT NULL,
                    listed_amount TEXT NOT NULL,
                    eligible_amount TEXT NOT NULL,
                    cash_component TEXT NOT NULL,
                    discount_rate TEXT NOT NULL,
                    price_after_discount TEXT NOT NULL,
                    base_points TEXT NOT NULL,
                    raw_bonus_points TEXT NOT NULL,
                    awarded_bonus_points TEXT NOT NULL,
                    capped_bonus_points TEXT NOT NULL,
                    total_points TEXT NOT NULL,
                    points_value_rupees TEXT NOT NULL,
                    net_cost TEXT NOT NULL,
                    cap_remaining_after TEXT NOT NULL,
                    explanation TEXT NOT NULL,
                    card_rank INTEGER,
                    FOREIGN KEY (recommendation_id) REFERENCES recommendations(id)
                );

                CREATE TABLE IF NOT EXISTS decisions (
                    recommendation_id TEXT PRIMARY KEY,
                    accepted INTEGER NOT NULL,
                    selected_option_id TEXT,
                    selected_card_id TEXT,
                    selected_vendor_id TEXT,
                    decline_reason TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (recommendation_id) REFERENCES recommendations(id)
                );

                CREATE TABLE IF NOT EXISTS transactions (
                    id TEXT PRIMARY KEY,
                    recommendation_id TEXT NOT NULL,
                    employee_id TEXT,
                    travel_type TEXT NOT NULL,
                    card_id TEXT NOT NULL,
                    vendor_id TEXT NOT NULL,
                    final_amount_paid TEXT NOT NULL,
                    discount_rate TEXT NOT NULL,
                    base_points TEXT NOT NULL,
                    bonus_points TEXT NOT NULL,
                    total_points TEXT NOT NULL,
                    points_value_rupees TEXT NOT NULL,
                    net_cost TEXT NOT NULL,
                    paid_at TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (recommendation_id) REFERENCES recommendations(id)
                );
                """
            )

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def _quote_to_json(self, quote: QuoteInput) -> dict[str, Any]:
        return {
            "vendor_id": quote.vendor_id,
            "amount": str(quote.amount),
            "merchant_name": quote.merchant_name,
            "description": quote.description,
            "discount_rate": str(quote.discount_rate),
        }

    def _option_row(
        self,
        recommendation_id: str,
        option: RecommendationOption,
        card_rank: int | None,
    ) -> tuple[Any, ...]:
        return (
            option.id,
            recommendation_id,
            option.rank,
            option.card_id,
            option.card_name,
            option.vendor_id,
            option.vendor_name,
            option.travel_type.value,
            str(option.listed_amount),
            str(option.eligible_amount),
            str(option.cash_component),
            str(option.discount_rate),
            str(option.price_after_discount),
            str(option.base_points),
            str(option.raw_bonus_points),
            str(option.awarded_bonus_points),
            str(option.capped_bonus_points),
            str(option.total_points),
            str(option.points_value_rupees),
            str(option.net_cost),
            str(option.cap_remaining_after),
            option.explanation,
            card_rank,
        )

    def _card_rank(self, recommendation: Recommendation, option: RecommendationOption) -> int | None:
        for card_option in recommendation.card_rankings:
            if card_option.id == option.id:
                return card_option.rank
        return None

    def _option_from_row(self, row: sqlite3.Row, rank_column: str) -> RecommendationOption:
        return RecommendationOption(
            id=row["id"],
            rank=row[rank_column],
            card_id=row["card_id"],
            card_name=row["card_name"],
            vendor_id=row["vendor_id"],
            vendor_name=row["vendor_name"],
            travel_type=TravelType(row["travel_type"]),
            listed_amount=Decimal(row["listed_amount"]),
            eligible_amount=Decimal(row["eligible_amount"]),
            cash_component=Decimal(row["cash_component"]),
            discount_rate=Decimal(row["discount_rate"]),
            price_after_discount=Decimal(row["price_after_discount"]),
            base_points=Decimal(row["base_points"]),
            raw_bonus_points=Decimal(row["raw_bonus_points"]),
            awarded_bonus_points=Decimal(row["awarded_bonus_points"]),
            capped_bonus_points=Decimal(row["capped_bonus_points"]),
            total_points=Decimal(row["total_points"]),
            points_value_rupees=Decimal(row["points_value_rupees"]),
            net_cost=Decimal(row["net_cost"]),
            cap_remaining_after=Decimal(row["cap_remaining_after"]),
            explanation=row["explanation"],
        )

    def _dict(self, row: sqlite3.Row) -> dict[str, Any]:
        return dict(row)
