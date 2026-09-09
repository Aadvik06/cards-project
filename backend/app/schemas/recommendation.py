from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field

from app.domain.enums import TravelType
from app.domain.models import (
    DecisionRecord,
    QuoteInput,
    Recommendation,
    RecommendationOption,
    TransactionRecord,
)


class QuoteRequest(BaseModel):
    vendor_id: str
    amount: Decimal = Field(gt=0)
    merchant_name: str | None = None
    description: str | None = None
    discount_rate: Decimal = Field(default=Decimal("0"), ge=0)
    voucher_face_value: Decimal | None = Field(default=None, ge=0)
    gst_invoice_available: bool = False
    origin_state: str | None = None
    destination_state: str | None = None
    hotel_state: str | None = None
    flight_class: str | None = None
    flight_sector_count: int = Field(default=1, ge=1, le=4)
    agent_payment_method: str | None = None
    agent_card_id: str | None = None

    def to_domain(self) -> QuoteInput:
        return QuoteInput(
            vendor_id=self.vendor_id,
            amount=self.amount,
            merchant_name=self.merchant_name,
            description=self.description,
            discount_rate=self.discount_rate,
            voucher_face_value=self.voucher_face_value,
            gst_invoice_available=self.gst_invoice_available,
            origin_state=self.origin_state,
            destination_state=self.destination_state,
            hotel_state=self.hotel_state,
            flight_class=self.flight_class,
            flight_sector_count=self.flight_sector_count,
            agent_payment_method=self.agent_payment_method,
            agent_card_id=self.agent_card_id,
        )


class RecommendationCreateRequest(BaseModel):
    employee_id: str | None = None
    employee_name: str | None = None
    travel_type: TravelType
    travel_date: date | None = None
    quotes: list[QuoteRequest] = Field(min_length=1)


class RecommendationOptionResponse(BaseModel):
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
    gst_rate: Decimal
    gst_credit: Decimal
    tax_benefit: Decimal
    deductible_expense: Decimal
    foreign_transaction: bool
    gst_claimable: bool
    gst_note: str
    net_cost: Decimal
    cap_remaining_after: Decimal
    explanation: str

    @classmethod
    def from_domain(cls, option: RecommendationOption) -> "RecommendationOptionResponse":
        return cls(**option.__dict__)


class RecommendationResponse(BaseModel):
    id: str
    employee_id: str | None
    travel_type: TravelType
    ranked_options: list[RecommendationOptionResponse]
    card_rankings: list[RecommendationOptionResponse]
    created_at: datetime

    @classmethod
    def from_domain(cls, recommendation: Recommendation) -> "RecommendationResponse":
        return cls(
            id=recommendation.id,
            employee_id=recommendation.employee_id,
            travel_type=recommendation.travel_type,
            ranked_options=[
                RecommendationOptionResponse.from_domain(option)
                for option in recommendation.ranked_options
            ],
            card_rankings=[
                RecommendationOptionResponse.from_domain(option)
                for option in recommendation.card_rankings
            ],
            created_at=recommendation.created_at,
        )


class DecisionRequest(BaseModel):
    accepted: bool
    selected_option_id: str | None = None
    selected_card_id: str | None = None
    selected_vendor_id: str | None = None
    decline_reason: str | None = None


class DecisionResponse(BaseModel):
    recommendation_id: str
    accepted: bool
    selected_option_id: str | None
    selected_card_id: str | None
    selected_vendor_id: str | None
    decline_reason: str | None
    created_at: datetime
    transaction_logged: bool = False
    next_step: str

    @classmethod
    def from_domain(cls, decision: DecisionRecord) -> "DecisionResponse":
        return cls(
            recommendation_id=decision.recommendation_id,
            accepted=decision.accepted,
            selected_option_id=decision.selected_option_id,
            selected_card_id=decision.selected_card_id,
            selected_vendor_id=decision.selected_vendor_id,
            decline_reason=decision.decline_reason,
            created_at=decision.created_at,
            next_step="Submit final amount paid to write the monthly transaction log.",
        )


class FinalizeTransactionRequest(BaseModel):
    final_amount_paid: Decimal = Field(gt=0)
    selected_option_id: str | None = None
    selected_card_id: str | None = None
    selected_vendor_id: str | None = None
    paid_at: datetime | None = None
    points_used: Decimal = Field(default=Decimal("0"), ge=0)
    details: dict[str, Any] = Field(default_factory=dict)


class VoucherLogRequest(BaseModel):
    employee_name: str | None = None
    vendor_name: str
    final_amount_paid: Decimal = Field(gt=0)
    paid_at: datetime | None = None
    description: str


class TransactionDetailsUpdateRequest(BaseModel):
    details: dict[str, str] = Field(default_factory=dict)


class TransactionResponse(BaseModel):
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
    points_used: Decimal
    gst_rate: Decimal
    gst_credit: Decimal
    tax_benefit: Decimal
    deductible_expense: Decimal
    foreign_transaction: bool
    net_cost: Decimal
    paid_at: datetime
    details: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    transaction_logged: bool = True

    @classmethod
    def from_domain(cls, transaction: TransactionRecord) -> "TransactionResponse":
        return cls(**transaction.__dict__)


class DraftSaveRequest(BaseModel):
    id: str | None = None
    title: str = Field(min_length=1)
    travel_type: str
    current_step: int = Field(default=1, ge=1, le=4)
    data: dict[str, Any] = Field(default_factory=dict)


class DraftResponse(BaseModel):
    id: str
    title: str
    travel_type: str
    current_step: int
    data: dict[str, Any]
    created_by: str | None = None
    created_at: datetime
    updated_at: datetime
