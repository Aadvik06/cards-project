import json
from decimal import Decimal
from pathlib import Path

from app.domain.enums import PurchaseForm, RefreshType, TravelType
from app.domain.models import CardVendorRule, CreditCard, Vendor, VoucherRule


SEED_DIR = Path(__file__).resolve().parents[1] / "seed"


class RulesRepository:
    def __init__(self, seed_dir: Path = SEED_DIR) -> None:
        self.seed_dir = seed_dir

    def cards(self) -> list[CreditCard]:
        return [
            CreditCard(
                id=row["id"],
                name=row["name"],
                base_rate=Decimal(row["base_rate"]),
                point_value_rupees=Decimal(row["point_value_rupees"]),
                daily_bonus_cap=Decimal(row["daily_bonus_cap"]),
                cycle_bonus_cap=Decimal(row["cycle_bonus_cap"]),
                refresh_type=RefreshType(row["refresh_type"]),
                statement_day=row["statement_day"],
                flight_multiplier=Decimal(row["flight_multiplier"]),
                hotel_multiplier=Decimal(row["hotel_multiplier"]),
            )
            for row in self._read_json("cards.json")
        ]

    def vendors(self) -> list[Vendor]:
        return [
            Vendor(
                id=row["id"],
                name=row["name"],
                travel_type=TravelType(row["travel_type"]),
                purchase_form=PurchaseForm(row["purchase_form"]),
            )
            for row in self._read_json("vendors.json")
        ]

    def card_vendor_rules(self) -> list[CardVendorRule]:
        return [
            CardVendorRule(
                card_id=row["card_id"],
                vendor_id=row["vendor_id"],
                multiplier_override=(
                    Decimal(row["multiplier_override"])
                    if row.get("multiplier_override") is not None
                    else None
                ),
            )
            for row in self._read_json("card_vendor_rules.json")
        ]

    def voucher_rules(self) -> list[VoucherRule]:
        return [
            VoucherRule(
                card_id=row["card_id"],
                vendor_id=row["vendor_id"],
                transaction_cap=Decimal(row["transaction_cap"]),
                description=row["description"],
            )
            for row in self._read_json("voucher_rules.json")
        ]

    def _read_json(self, filename: str) -> list[dict]:
        with (self.seed_dir / filename).open("r", encoding="utf-8") as handle:
            return json.load(handle)

