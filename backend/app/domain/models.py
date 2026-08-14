from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

from app.domain.enums import PurchaseForm, RefreshType, TravelType


@dataclass(frozen=True)
class CreditCard:
    id: str
    name: str
    base_rate: Decimal
    point_value_rupees: Decimal
    daily_bonus_cap: Decimal
    cycle_bonus_cap: Decimal
    refresh_type: RefreshType
    statement_day: int | None
    flight_multiplier: Decimal
    hotel_multiplier: Decimal

    def multiplier_for(self, travel_type: TravelType) -> Decimal:
        if travel_type == TravelType.FLIGHT:
            return self.flight_multiplier
        return self.hotel_multiplier


@dataclass(frozen=True)
class Vendor:
    id: str
    name: str
    travel_type: TravelType
    purchase_form: PurchaseForm


@dataclass(frozen=True)
class CardVendorRule:
    card_id: str
    vendor_id: str
    multiplier_override: Decimal | None = None


@dataclass(frozen=True)
class VoucherRule:
    card_id: str
    vendor_id: str
    transaction_cap: Decimal
    description: str


@dataclass(frozen=True)
class UsageSnapshot:
    daily_bonus_points_used: Decimal = Decimal("0")
    cycle_bonus_points_used: Decimal = Decimal("0")


@dataclass(frozen=True)
class QuoteInput:
    vendor_id: str
    amount: Decimal
    merchant_name: str | None = None
    description: str | None = None
    discount_rate: Decimal = Decimal("0")


@dataclass(frozen=True)
class RecommendationOption:
    id: str
    rank: int
    card_id: str
    card_name: str
    vendor_id: str
    vendor_name: str
    travel_type: TravelType
    listed_amount: Decimal
    eligible_amount: Decimal
    cash_component: Decimal
    discount_rate: Decimal
    price_after_discount: Decimal
    base_points: Decimal
    raw_bonus_points: Decimal
    awarded_bonus_points: Decimal
    capped_bonus_points: Decimal
    total_points: Decimal
    points_value_rupees: Decimal
    net_cost: Decimal
    cap_remaining_after: Decimal
    explanation: str


@dataclass
class Recommendation:
    id: str
    employee_id: str | None
    travel_type: TravelType
    quotes: list[QuoteInput]
    ranked_options: list[RecommendationOption]
    card_rankings: list[RecommendationOption]
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @classmethod
    def create(
        cls,
        *,
        employee_id: str | None,
        travel_type: TravelType,
        quotes: list[QuoteInput],
        ranked_options: list[RecommendationOption],
        card_rankings: list[RecommendationOption],
    ) -> "Recommendation":
        return cls(
            id=str(uuid4()),
            employee_id=employee_id,
            travel_type=travel_type,
            quotes=quotes,
            ranked_options=ranked_options,
            card_rankings=card_rankings,
        )


@dataclass(frozen=True)
class DecisionRecord:
    recommendation_id: str
    accepted: bool
    selected_option_id: str | None
    selected_card_id: str | None
    selected_vendor_id: str | None
    decline_reason: str | None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True)
class TransactionRecord:
    id: str
    recommendation_id: str
    employee_id: str | None
    travel_type: TravelType
    card_id: str
    vendor_id: str
    final_amount_paid: Decimal
    discount_rate: Decimal
    base_points: Decimal
    bonus_points: Decimal
    total_points: Decimal
    points_value_rupees: Decimal
    net_cost: Decimal
    paid_at: datetime
    details: dict[str, str] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
