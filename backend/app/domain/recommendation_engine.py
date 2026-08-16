from dataclasses import replace
from decimal import Decimal
from uuid import uuid4

from app.core.decimal_math import money, points
from app.core.errors import OptimizerError
from app.domain.enums import TravelType
from app.domain.models import (
    CardVendorRule,
    CreditCard,
    QuoteInput,
    Recommendation,
    RecommendationOption,
    UsageSnapshot,
    Vendor,
    VoucherRule,
)
from app.domain.reward_calculator import RewardCalculator
from app.domain.tie_breaker import option_sort_key


AGENT_VENDOR_BY_TYPE = {
    TravelType.FLIGHT: "travel_agent_flight",
    TravelType.HOTEL: "travel_agent_hotel",
}
AGENT_CARD_ID = "bank_transfer"
AGENT_CARD_NAME = "Bank Transfer"
AGENT_VENDOR_NAME = "Travel Agent"


class RecommendationEngine:
    def __init__(
        self,
        *,
        cards: list[CreditCard],
        vendors: list[Vendor],
        card_vendor_rules: list[CardVendorRule],
        voucher_rules: list[VoucherRule],
        calculator: RewardCalculator | None = None,
    ) -> None:
        self.cards = {card.id: card for card in cards}
        self.vendors = {vendor.id: vendor for vendor in vendors}
        self.card_vendor_rules = card_vendor_rules
        self.voucher_rules = {
            (rule.card_id, rule.vendor_id): rule for rule in voucher_rules
        }
        self.calculator = calculator or RewardCalculator()

    def rank(
        self,
        *,
        employee_id: str | None,
        travel_type: TravelType,
        quotes: list[QuoteInput],
        usage_by_card: dict[str, UsageSnapshot] | None = None,
    ) -> Recommendation:
        usage_by_card = usage_by_card or {}
        if not quotes:
            raise OptimizerError("At least one quote is required.")

        options: list[RecommendationOption] = []
        for quote in quotes:
            if quote.vendor_id == AGENT_VENDOR_BY_TYPE.get(travel_type):
                options.append(self._agent_option(quote=quote, travel_type=travel_type))
                continue

            vendor = self._vendor_for_quote(quote, travel_type)
            eligible_rules = [
                rule for rule in self.card_vendor_rules if rule.vendor_id == vendor.id
            ]
            for rule in eligible_rules:
                card = self.cards[rule.card_id]
                options.append(
                    self.calculator.calculate(
                        card=card,
                        vendor=vendor,
                        quote=quote,
                        travel_type=travel_type,
                        usage=usage_by_card.get(card.id, UsageSnapshot()),
                        voucher_rule=self.voucher_rules.get((card.id, vendor.id)),
                        multiplier_override=rule.multiplier_override,
                    )
                )

        if not options:
            raise OptimizerError("No eligible card/vendor options found.")

        ranked_options = [
            replace(option, rank=index)
            for index, option in enumerate(sorted(options, key=option_sort_key), start=1)
        ]

        best_by_card: dict[str, RecommendationOption] = {}
        for option in ranked_options:
            best_by_card.setdefault(option.card_id, option)

        card_rankings = [
            replace(option, rank=index)
            for index, option in enumerate(
                sorted(best_by_card.values(), key=option_sort_key), start=1
            )
        ]

        return Recommendation.create(
            employee_id=employee_id,
            travel_type=travel_type,
            quotes=quotes,
            ranked_options=ranked_options,
            card_rankings=card_rankings,
        )

    def _agent_option(self, *, quote: QuoteInput, travel_type: TravelType) -> RecommendationOption:
        return RecommendationOption(
            id=str(uuid4()),
            rank=0,
            card_id=AGENT_CARD_ID,
            card_name=AGENT_CARD_NAME,
            vendor_id=quote.vendor_id,
            vendor_name=AGENT_VENDOR_NAME,
            travel_type=travel_type,
            listed_amount=money(quote.amount),
            eligible_amount=money(quote.amount),
            cash_component=money(Decimal("0")),
            discount_rate=Decimal("0"),
            price_after_discount=money(quote.amount),
            base_points=points(Decimal("0")),
            raw_bonus_points=points(Decimal("0")),
            awarded_bonus_points=points(Decimal("0")),
            capped_bonus_points=points(Decimal("0")),
            total_points=points(Decimal("0")),
            points_value_rupees=money(Decimal("0")),
            net_cost=money(quote.amount),
            cap_remaining_after=points(Decimal("0")),
            explanation=(
                "Travel Agent is paid by direct bank transfer. Net cost equals the agent price, "
                "with no card rewards or bonus cap impact."
            ),
        )

    def _vendor_for_quote(self, quote: QuoteInput, travel_type: TravelType) -> Vendor:
        vendor = self.vendors.get(quote.vendor_id)
        if vendor is None:
            raise OptimizerError(f"Unknown vendor: {quote.vendor_id}")
        if vendor.travel_type != travel_type:
            raise OptimizerError(
                f"Vendor {vendor.name} is for {vendor.travel_type}, not {travel_type}."
            )
        return vendor
