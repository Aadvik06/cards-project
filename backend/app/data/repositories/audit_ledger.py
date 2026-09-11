import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterator
from uuid import uuid4

from app.domain.enums import TravelType
from app.domain.models import (
    DecisionRecord,
    QuoteInput,
    Recommendation,
    RecommendationOption,
    TransactionRecord,
)


POSTGRES_AUDIT_TABLES = (
    "recommendations",
    "recommendation_options",
    "decisions",
    "transactions",
    "drafts",
    "transaction_invoices",
)


class InvoiceStorageLimitError(ValueError):
    """Raised when an invoice would exceed the reserved archive allocation."""


class AuditLedger:
    def __init__(
        self,
        db_path: Path | str | None = None,
        database_url: str | None = None,
    ) -> None:
        self.database_url = database_url or (os.environ.get("DATABASE_URL") if db_path is None else None)
        self.db_path: Path | None = None

        if self.database_url is None:
            self.db_path = Path(db_path or "data/runtime/cards_project.sqlite3")
            if self.db_path.exists() and self.db_path.is_dir():
                self.db_path = self.db_path / "cards_project.sqlite3"
            elif self.db_path.suffix == "":
                self.db_path = self.db_path / "cards_project.sqlite3"
            self.db_path.parent.mkdir(parents=True, exist_ok=True)

        self._initialize()

    def save_recommendation(self, recommendation: Recommendation) -> None:
        with self._connect() as connection:
            connection.execute(
                self._upsert_recommendation_sql(),
                (
                    recommendation.id,
                    recommendation.employee_id,
                    recommendation.travel_type.value,
                    json.dumps([self._quote_to_json(quote) for quote in recommendation.quotes]),
                    recommendation.created_at.isoformat(),
                ),
            )
            connection.execute(
                self._sql("DELETE FROM recommendation_options WHERE recommendation_id = ?"),
                (recommendation.id,),
            )
            option_sql = self._sql(
                """
                INSERT INTO recommendation_options (
                    id, recommendation_id, rank, card_id, card_name, vendor_id, vendor_name,
                    travel_type, listed_amount, eligible_amount, cash_component, discount_rate,
                    price_after_discount, base_points, raw_bonus_points, awarded_bonus_points,
                    capped_bonus_points, total_points, points_value_rupees, gst_credit,
                    gst_rate, tax_benefit, deductible_expense, foreign_transaction,
                    gst_claimable, gst_note, net_cost,
                    cap_remaining_after, explanation, card_rank
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """
            )
            option_rows = [
                self._option_row(recommendation.id, option, self._card_rank(recommendation, option))
                for option in recommendation.ranked_options
            ]
            if self.database_url:
                for option_row in option_rows:
                    connection.execute(option_sql, option_row)
            else:
                connection.executemany(option_sql, option_rows)

    def get_recommendation(self, recommendation_id: str) -> Recommendation | None:
        with self._connect() as connection:
            row = connection.execute(
                self._sql("SELECT * FROM recommendations WHERE id = ?"),
                (recommendation_id,),
            ).fetchone()
            if row is None:
                return None

            option_rows = connection.execute(
                self._sql(
                    """
                SELECT * FROM recommendation_options
                WHERE recommendation_id = ?
                ORDER BY rank ASC
                """
                ),
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
                    voucher_face_value=Decimal(quote["voucher_face_value"]) if quote.get("voucher_face_value") else None,
                    gst_invoice_available=bool(quote.get("gst_invoice_available")),
                    origin_state=quote.get("origin_state"),
                    destination_state=quote.get("destination_state"),
                    hotel_state=quote.get("hotel_state"),
                    flight_class=quote.get("flight_class"),
                    flight_sector_count=quote.get("flight_sector_count", 1),
                    agent_payment_method=quote.get("agent_payment_method"),
                    agent_card_id=quote.get("agent_card_id"),
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
                self._upsert_decision_sql(),
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
                self._sql(
                    """
                INSERT INTO transactions (
                    id, recommendation_id, employee_id, travel_type, card_id, vendor_id,
                    final_amount_paid, discount_rate, base_points, bonus_points, total_points,
                    points_value_rupees, points_used, gst_rate, gst_credit, tax_benefit,
                    deductible_expense, foreign_transaction, net_cost, paid_at, details_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """
                ),
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
                    str(transaction.points_used),
                    str(transaction.gst_rate),
                    str(transaction.gst_credit),
                    str(transaction.tax_benefit),
                    str(transaction.deductible_expense),
                    int(transaction.foreign_transaction),
                    str(transaction.net_cost),
                    transaction.paid_at.isoformat(),
                    json.dumps(transaction.details),
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
                self._sql("SELECT * FROM decisions WHERE recommendation_id = ?"),
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
            invoices = connection.execute("SELECT id, transaction_id, filename, content_type, uploaded_at, storage_path, storage_size_bytes FROM transaction_invoice_files ORDER BY uploaded_at ASC").fetchall()
            legacy_invoices = connection.execute("SELECT transaction_id, filename, content_type, uploaded_at, storage_path, storage_size_bytes FROM transaction_invoices").fetchall()
        invoice_by_transaction: dict[str, list[dict[str, Any]]] = {}
        for row in invoices:
            invoice = self._dict(row)
            invoice_by_transaction.setdefault(invoice["transaction_id"], []).append(invoice)
        for row in legacy_invoices:
            invoice = self._dict(row)
            invoice["id"] = f"legacy:{invoice['transaction_id']}"
            invoice_by_transaction.setdefault(invoice["transaction_id"], []).append(invoice)
        transactions = [self._dict(row) for row in rows]
        for transaction in transactions:
            files = invoice_by_transaction.get(transaction["id"], [])
            transaction["invoice_status"] = "uploaded" if files else "pending"
            transaction["invoice"] = files[0] if files else None
            transaction["invoices"] = files
        return transactions

    def invoice_storage_summary(self, allocation_bytes: int) -> dict[str, int]:
        """Return invoice usage within the deliberately reserved archive allocation."""
        with self._connect() as connection:
            row = connection.execute(
            "SELECT COALESCE(SUM(COALESCE(storage_size_bytes, LENGTH(file_data))), 0) AS used_bytes, COUNT(*) AS invoice_count FROM transaction_invoices"
            ).fetchone()
        used_bytes = int(row["used_bytes"] or 0)
        return {
            "used_bytes": used_bytes,
            "invoice_count": int(row["invoice_count"] or 0),
            "allocation_bytes": allocation_bytes,
            "remaining_bytes": max(allocation_bytes - used_bytes, 0),
        }

    def keepalive(self) -> None:
        """Run a minimal database query for the production maintenance job."""
        with self._connect() as connection:
            connection.execute("SELECT 1 FROM transactions LIMIT 1").fetchone()

    def save_invoice(
        self,
        *,
        transaction_id: str,
        filename: str,
        content_type: str,
        content: bytes,
        allocation_bytes: int | None = None,
    ) -> dict[str, Any]:
        filename = self.next_invoice_filename(transaction_id, filename)
        with self._connect() as connection:
            exists = connection.execute(
                self._sql("SELECT id FROM transactions WHERE id = ?"),
                (transaction_id,),
            ).fetchone()
            if exists is None:
                raise ValueError("Transaction not found.")
            if allocation_bytes is not None:
                previous = connection.execute(
                    self._sql("SELECT LENGTH(file_data) AS file_size_bytes FROM transaction_invoices WHERE transaction_id = ?"),
                    (transaction_id,),
                ).fetchone()
                totals = connection.execute(
                    "SELECT COALESCE(SUM(LENGTH(file_data)), 0) AS used_bytes FROM transaction_invoices"
                ).fetchone()
                previous_size = int(previous["file_size_bytes"] or 0) if previous else 0
                proposed_size = int(totals["used_bytes"] or 0) - previous_size + len(content)
                if proposed_size > allocation_bytes:
                    raise InvoiceStorageLimitError(
                        "The invoice archive is full. Download and delete older invoices before uploading another file."
                    )
            uploaded_at = datetime.now().isoformat()
            if self.database_url:
                connection.execute(
                    """
                    INSERT INTO transaction_invoices (
                        transaction_id, filename, content_type, file_data, uploaded_at
                    ) VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (transaction_id) DO UPDATE SET
                        filename = EXCLUDED.filename,
                        content_type = EXCLUDED.content_type,
                        file_data = EXCLUDED.file_data,
                        uploaded_at = EXCLUDED.uploaded_at
                    """,
                    (transaction_id, filename, content_type, content, uploaded_at),
                )
            else:
                connection.execute(
                    """
                    INSERT INTO transaction_invoices (
                        transaction_id, filename, content_type, file_data, uploaded_at
                    ) VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(transaction_id) DO UPDATE SET
                        filename = excluded.filename,
                        content_type = excluded.content_type,
                        file_data = excluded.file_data,
                        uploaded_at = excluded.uploaded_at
                    """,
                    (transaction_id, filename, content_type, content, uploaded_at),
                )
        return {
            "transaction_id": transaction_id,
            "filename": filename,
            "content_type": content_type,
            "uploaded_at": uploaded_at,
            "invoice_status": "uploaded",
        }

    def get_invoice(self, transaction_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                self._sql("SELECT * FROM transaction_invoices WHERE transaction_id = ?"),
                (transaction_id,),
            ).fetchone()
        return self._dict(row) if row is not None else None

    def save_cloud_invoice(self, *, transaction_id: str, filename: str, content_type: str, storage_path: str, file_size_bytes: int) -> dict[str, Any]:
        filename = self.next_invoice_filename(transaction_id, filename)
        with self._connect() as connection:
            exists = connection.execute(self._sql("SELECT id FROM transactions WHERE id = ?"), (transaction_id,)).fetchone()
            if exists is None:
                raise ValueError("Transaction not found.")
            uploaded_at = datetime.now().isoformat()
            invoice_id = str(uuid4())
            placeholders = "%s, %s, %s, %s, %s, %s, %s" if self.database_url else "?, ?, ?, ?, ?, ?, ?"
            connection.execute(
                f"INSERT INTO transaction_invoice_files (id, transaction_id, filename, content_type, storage_path, storage_size_bytes, uploaded_at) VALUES ({placeholders})",
                (invoice_id, transaction_id, filename, content_type, storage_path, file_size_bytes, uploaded_at),
            )
        return {"id": invoice_id, "transaction_id": transaction_id, "filename": filename, "content_type": content_type, "uploaded_at": uploaded_at, "invoice_status": "uploaded", "storage_path": storage_path, "storage_size_bytes": file_size_bytes}

    def next_invoice_filename(self, transaction_id: str, original_filename: str) -> str:
        """Build a consistent, audit-friendly name without loading invoice data."""
        with self._connect() as connection:
            transaction = connection.execute(
                self._sql("SELECT * FROM transactions WHERE id = ?"), (transaction_id,)
            ).fetchone()
            if transaction is None:
                raise ValueError("Transaction not found.")
            cloud_count = connection.execute(
                self._sql("SELECT COUNT(*) AS count FROM transaction_invoice_files WHERE transaction_id = ?"),
                (transaction_id,),
            ).fetchone()["count"]
            legacy_count = connection.execute(
                self._sql("SELECT COUNT(*) AS count FROM transaction_invoices WHERE transaction_id = ?"),
                (transaction_id,),
            ).fetchone()["count"]
        return self._invoice_filename(self._dict(transaction), int(cloud_count) + int(legacy_count) + 1, original_filename)

    def read_invoices(self) -> list[dict[str, Any]]:
        """Return audit-friendly invoice metadata without loading file contents."""
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT transaction_invoices.transaction_id, transaction_invoices.filename,
                       transaction_invoices.content_type, transaction_invoices.uploaded_at,
                       COALESCE(transaction_invoices.storage_size_bytes, LENGTH(transaction_invoices.file_data)) AS file_size_bytes,
                       transactions.paid_at, transactions.card_id
                FROM transaction_invoices
                INNER JOIN transactions ON transactions.id = transaction_invoices.transaction_id
                ORDER BY transactions.paid_at DESC
                """
            ).fetchall()
        return [self._dict(row) for row in rows]

    def read_cloud_invoices(self) -> list[dict[str, Any]]:
        with self._connect() as connection:
            cloud_rows = connection.execute("""
                SELECT transaction_invoice_files.id, transaction_invoice_files.transaction_id, transaction_invoice_files.filename,
                       transaction_invoice_files.content_type, transaction_invoice_files.storage_path, transaction_invoice_files.storage_size_bytes AS file_size_bytes,
                       transaction_invoice_files.uploaded_at, transactions.paid_at, transactions.card_id
                FROM transaction_invoice_files INNER JOIN transactions ON transactions.id = transaction_invoice_files.transaction_id
                ORDER BY transactions.paid_at DESC, transaction_invoice_files.uploaded_at ASC
            """).fetchall()
            legacy_rows = connection.execute("""
                SELECT transaction_invoices.transaction_id, transaction_invoices.filename, transaction_invoices.content_type,
                       transaction_invoices.storage_path, COALESCE(transaction_invoices.storage_size_bytes, LENGTH(transaction_invoices.file_data)) AS file_size_bytes,
                       transaction_invoices.uploaded_at, transactions.paid_at, transactions.card_id
                FROM transaction_invoices INNER JOIN transactions ON transactions.id = transaction_invoices.transaction_id
            """).fetchall()
        invoices = [self._dict(row) for row in cloud_rows]
        for row in legacy_rows:
            invoice = self._dict(row)
            invoice["id"] = f"legacy:{invoice['transaction_id']}"
            invoices.append(invoice)
        return sorted(invoices, key=lambda invoice: (invoice["paid_at"], invoice["uploaded_at"]), reverse=True)

    def get_cloud_invoice(self, invoice_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(self._sql("SELECT * FROM transaction_invoice_files WHERE id = ?"), (invoice_id,)).fetchone()
        return self._dict(row) if row is not None else None

    def delete_cloud_invoice(self, invoice_id: str) -> bool:
        with self._connect() as connection:
            cursor = connection.execute(self._sql("DELETE FROM transaction_invoice_files WHERE id = ?"), (invoice_id,))
            return cursor.rowcount > 0

    def delete_invoice(self, transaction_id: str) -> bool:
        with self._connect() as connection:
            cursor = connection.execute(
                self._sql("DELETE FROM transaction_invoices WHERE transaction_id = ?"),
                (transaction_id,),
            )
            return cursor.rowcount > 0

    def delete_transaction(self, transaction_id: str) -> bool:
        with self._connect() as connection:
            cursor = connection.execute(
                self._sql("DELETE FROM transactions WHERE id = ?"),
                (transaction_id,),
            )
            return cursor.rowcount > 0

    def update_transaction_details(self, transaction_id: str, updates: dict[str, str]) -> bool:
        with self._connect() as connection:
            row = connection.execute(
                self._sql("SELECT details_json FROM transactions WHERE id = ?"),
                (transaction_id,),
            ).fetchone()
            if row is None:
                return False
            details = json.loads(row["details_json"] or "{}")
            details.update(updates)
            cursor = connection.execute(
                self._sql("UPDATE transactions SET details_json = ? WHERE id = ?"),
                (json.dumps(details), transaction_id),
            )
            return cursor.rowcount > 0

    def save_draft(
        self,
        *,
        draft_id: str | None,
        title: str,
        travel_type: str,
        current_step: int,
        data: dict[str, Any],
        created_by: str | None = None,
    ) -> dict[str, Any]:
        now = datetime.now().isoformat()
        draft_id = draft_id or str(uuid4())
        with self._connect() as connection:
            connection.execute(
                self._upsert_draft_sql(),
                (
                    draft_id,
                    title,
                    travel_type,
                    current_step,
                    json.dumps(data),
                    created_by,
                    now,
                    now,
                ),
            )
        draft = self.get_draft(draft_id)
        if draft is None:
            raise RuntimeError("Draft could not be saved.")
        return draft

    def read_drafts(self) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM drafts ORDER BY updated_at DESC"
            ).fetchall()
        return [self._dict(row) for row in rows]

    def get_draft(self, draft_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                self._sql("SELECT * FROM drafts WHERE id = ?"),
                (draft_id,),
            ).fetchone()
        return self._dict(row) if row is not None else None

    def delete_draft(self, draft_id: str) -> bool:
        with self._connect() as connection:
            cursor = connection.execute(
                self._sql("DELETE FROM drafts WHERE id = ?"),
                (draft_id,),
            )
            return cursor.rowcount > 0

    def monthly_transactions(self, year: int, month: int) -> list[dict[str, Any]]:
        rows = []
        for row in self.read_transactions():
            paid_at = datetime.fromisoformat(row["paid_at"])
            if paid_at.year == year and paid_at.month == month:
                rows.append(row)
        return rows

    def _initialize(self) -> None:
        with self._connect() as connection:
            self._run_schema(connection)
            self._ensure_column(connection, "transactions", "details_json", "TEXT NOT NULL DEFAULT '{}'")
            self._ensure_column(connection, "recommendation_options", "gst_credit", "TEXT NOT NULL DEFAULT '0'")
            self._ensure_column(connection, "recommendation_options", "tax_benefit", "TEXT NOT NULL DEFAULT '0'")
            self._ensure_column(connection, "recommendation_options", "gst_claimable", "INTEGER NOT NULL DEFAULT 0")
            self._ensure_column(connection, "recommendation_options", "gst_note", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column(connection, "recommendation_options", "gst_rate", "TEXT NOT NULL DEFAULT '0'")
            self._ensure_column(connection, "recommendation_options", "deductible_expense", "TEXT NOT NULL DEFAULT '0'")
            self._ensure_column(connection, "recommendation_options", "foreign_transaction", "INTEGER NOT NULL DEFAULT 0")
            self._ensure_column(connection, "transactions", "points_used", "TEXT NOT NULL DEFAULT '0'")
            self._ensure_column(connection, "transactions", "gst_rate", "TEXT NOT NULL DEFAULT '0'")
            self._ensure_column(connection, "transactions", "gst_credit", "TEXT NOT NULL DEFAULT '0'")
            self._ensure_column(connection, "transactions", "tax_benefit", "TEXT NOT NULL DEFAULT '0'")
            self._ensure_column(connection, "transactions", "deductible_expense", "TEXT NOT NULL DEFAULT '0'")
            self._ensure_column(connection, "transactions", "foreign_transaction", "INTEGER NOT NULL DEFAULT 0")
            self._ensure_column(connection, "transaction_invoices", "storage_path", "TEXT")
            self._ensure_column(connection, "transaction_invoices", "storage_size_bytes", "INTEGER")
            self._rename_existing_invoice_records(connection)
            if self.database_url:
                self._enable_postgres_row_level_security(connection)

    def _rename_existing_invoice_records(self, connection: Any) -> None:
        """Give prior invoices the same download names as newly uploaded files.

        Storage object paths intentionally remain opaque; the database filename is
        what users see and what is applied to secure downloads and ZIP exports.
        """
        transactions = connection.execute(
            "SELECT id, travel_type, card_id, vendor_id, paid_at, details_json FROM transactions"
        ).fetchall()
        for transaction_row in transactions:
            transaction = self._dict(transaction_row)
            transaction_id = transaction["id"]
            cloud_rows = connection.execute(
                self._sql("SELECT id, filename, uploaded_at FROM transaction_invoice_files WHERE transaction_id = ? ORDER BY uploaded_at ASC"),
                (transaction_id,),
            ).fetchall()
            legacy_rows = connection.execute(
                self._sql("SELECT filename, uploaded_at FROM transaction_invoices WHERE transaction_id = ? ORDER BY uploaded_at ASC"),
                (transaction_id,),
            ).fetchall()
            files = [
                ("cloud", self._dict(row)) for row in cloud_rows
            ] + [("legacy", self._dict(row)) for row in legacy_rows]
            files.sort(key=lambda item: item[1]["uploaded_at"])
            for sequence, (kind, invoice) in enumerate(files, start=1):
                filename = self._invoice_filename(transaction, sequence, invoice["filename"])
                if invoice["filename"] == filename:
                    continue
                if kind == "cloud":
                    connection.execute(
                        self._sql("UPDATE transaction_invoice_files SET filename = ? WHERE id = ?"),
                        (filename, invoice["id"]),
                    )
                else:
                    connection.execute(
                        self._sql("UPDATE transaction_invoices SET filename = ? WHERE transaction_id = ?"),
                        (filename, transaction_id),
                    )

    @staticmethod
    def _invoice_filename(transaction: dict[str, Any], sequence: int, original_filename: str) -> str:
        details = transaction.get("details") or {}
        extension = Path(original_filename or "").suffix.lower()
        if extension not in {".pdf", ".jpg", ".jpeg", ".png", ".webp"}:
            extension = ".pdf"
        travel_type = transaction.get("travel_type")
        if travel_type == "flight":
            subject = "-".join(value for value in (details.get("from"), details.get("to")) if value) or "Flight"
            travel_date = details.get("flight_date") or transaction.get("paid_at")
        elif travel_type == "hotel":
            subject = details.get("hotel_name") or details.get("city") or "Hotel"
            travel_date = details.get("check_in") or transaction.get("paid_at")
        else:
            subject = details.get("vendor_name") or "Voucher"
            travel_date = details.get("purchase_date") or transaction.get("paid_at")
        date_text = str(travel_date or "").split("T", 1)[0] or "Undated"
        card_name = {
            "amex": "American-Express",
            "hdfc_infinia": "HDFC-Infinia",
            "icici_times_black": "ICICI-Times-Black",
            "bank_transfer": "Bank-Transfer",
        }.get(transaction.get("card_id"), transaction.get("card_id") or "Payment")
        vendor_name = details.get("travel_agent_name") or AuditLedger._vendor_filename_name(transaction.get("vendor_id") or "Vendor")
        traveller = details.get("booking_for") or ""
        parts = [date_text, card_name, vendor_name]
        if traveller:
            parts.append(traveller)
        parts.extend([subject, f"Invoice-T{sequence:02d}"])
        safe_name = "_".join(AuditLedger._safe_filename_part(part) for part in parts if part)
        return f"{safe_name[: max(1, 200 - len(extension))]}{extension}"

    @staticmethod
    def _vendor_filename_name(vendor_id: str) -> str:
        names = {
            "amex_mmt_flight_voucher": "MakeMyTrip",
            "amex_cleartrip_generic_voucher": "Cleartrip",
            "hdfc_smartbuy_flight": "HDFC-SmartBuy",
            "icici_ishop_flight": "ICICI-iShop",
            "travel_agent_flight": "Travel-Agent",
            "amex_goibibo_hotel_voucher": "Goibibo",
            "amex_easemytrip_hotel_voucher": "EaseMyTrip",
            "amex_mmt_hotel_voucher": "MakeMyTrip",
            "amex_cleartrip_hotel_voucher": "Cleartrip",
            "hdfc_smartbuy_hotel": "HDFC-SmartBuy",
            "icici_ishop_hotel": "ICICI-iShop",
            "amex_fine_hotels": "Amex-Fine-Hotels",
            "travel_agent_hotel": "Travel-Agent",
            "amex_other_voucher": "American-Express-Voucher",
        }
        return names.get(vendor_id, vendor_id.replace("_", "-"))

    @staticmethod
    def _safe_filename_part(value: Any) -> str:
        clean = "".join(character if character.isalnum() else "-" for character in str(value).strip())
        clean = "-".join(part for part in clean.split("-") if part)
        return clean[:48] or "Unknown"

    @contextmanager
    def _connect(self) -> Iterator[Any]:
        if self.database_url:
            try:
                import psycopg
                from psycopg.rows import dict_row
            except ImportError as exc:
                raise RuntimeError(
                    "psycopg is required when DATABASE_URL is set. Install backend/requirements.txt."
                ) from exc

            connection = psycopg.connect(
                self._postgres_url(),
                row_factory=dict_row,
                prepare_threshold=None,
            )
        else:
            connection = sqlite3.connect(self.db_path)
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys = ON")

        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def _sql(self, sql: str) -> str:
        if self.database_url:
            return sql.replace("?", "%s")
        return sql

    def _postgres_url(self) -> str:
        if not self.database_url:
            raise RuntimeError("DATABASE_URL is not configured.")
        if "sslmode=" in self.database_url:
            return self.database_url
        separator = "&" if "?" in self.database_url else "?"
        return f"{self.database_url}{separator}sslmode=require"

    def _enable_postgres_row_level_security(self, connection: Any) -> None:
        """Deny direct PostgREST access to private audit tables.

        The web application accesses these tables only through its server-side
        PostgreSQL connection. RLS therefore has no client policies: Supabase's
        anon/authenticated API roles cannot read or write corporate travel data.
        """
        for table_name in POSTGRES_AUDIT_TABLES:
            connection.execute(f"ALTER TABLE public.{table_name} ENABLE ROW LEVEL SECURITY")

    def _upsert_recommendation_sql(self) -> str:
        if self.database_url:
            return """
                INSERT INTO recommendations (
                    id, employee_id, travel_type, quotes_json, created_at
                ) VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET
                    employee_id = EXCLUDED.employee_id,
                    travel_type = EXCLUDED.travel_type,
                    quotes_json = EXCLUDED.quotes_json,
                    created_at = EXCLUDED.created_at
                """
        return """
            INSERT OR REPLACE INTO recommendations (
                id, employee_id, travel_type, quotes_json, created_at
            ) VALUES (?, ?, ?, ?, ?)
            """

    def _upsert_decision_sql(self) -> str:
        if self.database_url:
            return """
                INSERT INTO decisions (
                    recommendation_id, accepted, selected_option_id, selected_card_id,
                    selected_vendor_id, decline_reason, created_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (recommendation_id) DO UPDATE SET
                    accepted = EXCLUDED.accepted,
                    selected_option_id = EXCLUDED.selected_option_id,
                    selected_card_id = EXCLUDED.selected_card_id,
                    selected_vendor_id = EXCLUDED.selected_vendor_id,
                    decline_reason = EXCLUDED.decline_reason,
                    created_at = EXCLUDED.created_at
                """
        return """
            INSERT OR REPLACE INTO decisions (
                recommendation_id, accepted, selected_option_id, selected_card_id,
            selected_vendor_id, decline_reason, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """

    def _upsert_draft_sql(self) -> str:
        if self.database_url:
            return """
                INSERT INTO drafts (
                    id, title, travel_type, current_step, data_json, created_by, created_at, updated_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET
                    title = EXCLUDED.title,
                    travel_type = EXCLUDED.travel_type,
                    current_step = EXCLUDED.current_step,
                    data_json = EXCLUDED.data_json,
                    created_by = EXCLUDED.created_by,
                    updated_at = EXCLUDED.updated_at
                """
        return """
            INSERT INTO drafts (
                id, title, travel_type, current_step, data_json, created_by, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                title = excluded.title,
                travel_type = excluded.travel_type,
                current_step = excluded.current_step,
                data_json = excluded.data_json,
                created_by = excluded.created_by,
                updated_at = excluded.updated_at
            """

    def _run_schema(self, connection: Any) -> None:
        statements = [
            """
            CREATE TABLE IF NOT EXISTS recommendations (
                id TEXT PRIMARY KEY,
                employee_id TEXT,
                travel_type TEXT NOT NULL,
                quotes_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """,
            """
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
                gst_rate TEXT NOT NULL DEFAULT '0',
                gst_credit TEXT NOT NULL DEFAULT '0',
                tax_benefit TEXT NOT NULL DEFAULT '0',
                deductible_expense TEXT NOT NULL DEFAULT '0',
                foreign_transaction INTEGER NOT NULL DEFAULT 0,
                gst_claimable INTEGER NOT NULL DEFAULT 0,
                gst_note TEXT NOT NULL DEFAULT '',
                net_cost TEXT NOT NULL,
                cap_remaining_after TEXT NOT NULL,
                explanation TEXT NOT NULL,
                card_rank INTEGER,
                FOREIGN KEY (recommendation_id) REFERENCES recommendations(id)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS decisions (
                recommendation_id TEXT PRIMARY KEY,
                accepted INTEGER NOT NULL,
                selected_option_id TEXT,
                selected_card_id TEXT,
                selected_vendor_id TEXT,
                decline_reason TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (recommendation_id) REFERENCES recommendations(id)
            )
            """,
            """
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
                points_used TEXT NOT NULL DEFAULT '0',
                gst_rate TEXT NOT NULL DEFAULT '0',
                gst_credit TEXT NOT NULL DEFAULT '0',
                tax_benefit TEXT NOT NULL DEFAULT '0',
                deductible_expense TEXT NOT NULL DEFAULT '0',
                foreign_transaction INTEGER NOT NULL DEFAULT 0,
                net_cost TEXT NOT NULL,
                paid_at TEXT NOT NULL,
                details_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                FOREIGN KEY (recommendation_id) REFERENCES recommendations(id)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS drafts (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                travel_type TEXT NOT NULL,
                current_step INTEGER NOT NULL,
                data_json TEXT NOT NULL,
                created_by TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """,
            f"""
            CREATE TABLE IF NOT EXISTS transaction_invoices (
                transaction_id TEXT PRIMARY KEY,
                filename TEXT NOT NULL,
                content_type TEXT NOT NULL,
                file_data {"BYTEA" if self.database_url else "BLOB"} NOT NULL,
                uploaded_at TEXT NOT NULL,
                FOREIGN KEY (transaction_id) REFERENCES transactions(id) ON DELETE CASCADE
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS transaction_invoice_files (
                id TEXT PRIMARY KEY,
                transaction_id TEXT NOT NULL,
                filename TEXT NOT NULL,
                content_type TEXT NOT NULL,
                storage_path TEXT NOT NULL,
                storage_size_bytes INTEGER NOT NULL,
                uploaded_at TEXT NOT NULL,
                FOREIGN KEY (transaction_id) REFERENCES transactions(id) ON DELETE CASCADE
            )
            """,
        ]
        for statement in statements:
            connection.execute(statement)

    def _quote_to_json(self, quote: QuoteInput) -> dict[str, Any]:
        return {
            "vendor_id": quote.vendor_id,
            "amount": str(quote.amount),
            "merchant_name": quote.merchant_name,
            "description": quote.description,
            "discount_rate": str(quote.discount_rate),
            "voucher_face_value": str(quote.voucher_face_value) if quote.voucher_face_value is not None else None,
            "gst_invoice_available": quote.gst_invoice_available,
            "origin_state": quote.origin_state,
            "destination_state": quote.destination_state,
            "hotel_state": quote.hotel_state,
            "flight_class": quote.flight_class,
            "flight_sector_count": quote.flight_sector_count,
            "agent_payment_method": quote.agent_payment_method,
            "agent_card_id": quote.agent_card_id,
        }

    def _ensure_column(
        self,
        connection: sqlite3.Connection,
        table_name: str,
        column_name: str,
        definition: str,
    ) -> None:
        columns = {
            row["column_name"] if self.database_url else row["name"]
            for row in connection.execute(
                self._sql(
                    """
                    SELECT column_name
                    FROM information_schema.columns
                    WHERE table_name = ?
                    """
                ) if self.database_url else f"PRAGMA table_info({table_name})",
                (table_name,) if self.database_url else (),
            ).fetchall()
        }
        if column_name not in columns:
            connection.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}")

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
            str(option.gst_rate),
            str(option.gst_credit),
            str(option.tax_benefit),
            str(option.deductible_expense),
            int(option.foreign_transaction),
            int(option.gst_claimable),
            option.gst_note,
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
            gst_rate=Decimal(row["gst_rate"]),
            gst_credit=Decimal(row["gst_credit"]),
            tax_benefit=Decimal(row["tax_benefit"]),
            deductible_expense=Decimal(row["deductible_expense"]),
            foreign_transaction=bool(row["foreign_transaction"]),
            gst_claimable=bool(row["gst_claimable"]),
            gst_note=row["gst_note"],
            net_cost=Decimal(row["net_cost"]),
            cap_remaining_after=Decimal(row["cap_remaining_after"]),
            explanation=row["explanation"],
        )

    def _dict(self, row: sqlite3.Row) -> dict[str, Any]:
        value = dict(row)
        if "details_json" in value:
            value["details"] = json.loads(value["details_json"] or "{}")
        if "data_json" in value:
            value["data"] = json.loads(value["data_json"] or "{}")
        return value
