from dataclasses import replace

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

    def _vendor_for_quote(self, quote: QuoteInput, travel_type: TravelType) -> Vendor:
        vendor = self.vendors.get(quote.vendor_id)
        if vendor is None:
            raise OptimizerError(f"Unknown vendor: {quote.vendor_id}")
        if vendor.travel_type != travel_type:
            raise OptimizerError(
                f"Vendor {vendor.name} is for {vendor.travel_type}, not {travel_type}."
            )
        return vendor

