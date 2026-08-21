from decimal import Decimal
from uuid import uuid4

from app.core.decimal_math import money, non_negative, points
from app.core.errors import OptimizerError
from app.domain.cap_tracker import remaining_bonus_cap
from app.domain.enums import TravelType
from app.domain.models import (
    CreditCard,
    QuoteInput,
    RecommendationOption,
    UsageSnapshot,
    Vendor,
    VoucherRule,
)


VOUCHER_FACE_VALUE_INCREMENT = Decimal("10000")
FLIGHT_GST_RATE = Decimal("0.05")
HOTEL_GST_RATE = Decimal("0.18")
CORPORATE_TAX_RATE = Decimal("0.275")
HOTEL_GST_REGISTERED_STATES = {
    "Maharashtra",
    "Daman",
    "Assam",
    "Gujarat",
    "Uttarakhand",
    "Himachal Pradesh",
}


class RewardCalculator:
    def calculate(
        self,
        *,
        card: CreditCard,
        vendor: Vendor,
        quote: QuoteInput,
        travel_type: TravelType,
        usage: UsageSnapshot,
        voucher_rule: VoucherRule | None = None,
        multiplier_override: Decimal | None = None,
    ) -> RecommendationOption:
        eligible_amount = quote.amount
        cash_component = Decimal("0")

        if voucher_rule is not None:
            inferred_voucher_value = (quote.amount // VOUCHER_FACE_VALUE_INCREMENT) * VOUCHER_FACE_VALUE_INCREMENT
            eligible_amount = quote.voucher_face_value if quote.voucher_face_value is not None else inferred_voucher_value
            if eligible_amount > quote.amount:
                raise OptimizerError("Voucher value cannot be higher than the booking price.")
            if eligible_amount > voucher_rule.transaction_cap:
                raise OptimizerError("Voucher value is higher than the allowed voucher cap for this vendor.")
            cash_component = non_negative(quote.amount - eligible_amount)

        discounted_eligible_amount = eligible_amount * (Decimal("1") - quote.discount_rate)
        price_after_discount = discounted_eligible_amount + cash_component

        base_points = price_after_discount * card.base_rate
        bonus_base_points = discounted_eligible_amount * card.base_rate
        multiplier = multiplier_override or card.multiplier_for(travel_type)
        raw_bonus_points = max(Decimal("0"), (bonus_base_points * multiplier) - bonus_base_points)
        available_bonus_cap = remaining_bonus_cap(card, usage)
        awarded_bonus_points = min(raw_bonus_points, available_bonus_cap)
        capped_bonus_points = non_negative(raw_bonus_points - awarded_bonus_points)
        total_points = base_points + awarded_bonus_points
        points_value_rupees = total_points * card.point_value_rupees
        gst_base_amount = self._gst_base_amount(
            quote=quote,
            price_after_discount=price_after_discount,
            eligible_amount=eligible_amount,
            cash_component=cash_component,
            voucher_rule=voucher_rule,
        )
        gst_credit, tax_benefit, gst_claimable, gst_note = self._gst_credit(
            quote=quote,
            travel_type=travel_type,
            gst_base_amount=gst_base_amount,
        )
        net_cost = price_after_discount - points_value_rupees - gst_credit - tax_benefit

        if capped_bonus_points:
            cap_note = f"{points(capped_bonus_points)} bonus points exceeded the remaining cap."
        else:
            cap_note = "No cap reduction applied."

        return RecommendationOption(
            id=str(uuid4()),
            rank=0,
            card_id=card.id,
            card_name=card.name,
            vendor_id=vendor.id,
            vendor_name=vendor.name,
            travel_type=travel_type,
            listed_amount=money(quote.amount),
            eligible_amount=money(eligible_amount),
            cash_component=money(cash_component),
            discount_rate=quote.discount_rate,
            price_after_discount=money(price_after_discount),
            base_points=points(base_points),
            raw_bonus_points=points(raw_bonus_points),
            awarded_bonus_points=points(awarded_bonus_points),
            capped_bonus_points=points(capped_bonus_points),
            total_points=points(total_points),
            points_value_rupees=money(points_value_rupees),
            gst_credit=money(gst_credit),
            tax_benefit=money(tax_benefit),
            gst_claimable=gst_claimable,
            gst_note=gst_note,
            net_cost=money(net_cost),
            cap_remaining_after=points(non_negative(available_bonus_cap - awarded_bonus_points)),
            explanation=(
                f"{card.name} through {vendor.name}: net cost equals price after discount "
                f"minus rupee value of points, claimable GST credit, and non-claimable GST tax benefit. {gst_note} {cap_note}"
            ),
        )

    def _gst_credit(
        self,
        *,
        quote: QuoteInput,
        travel_type: TravelType,
        gst_base_amount: Decimal,
    ) -> tuple[Decimal, Decimal, bool, str]:
        gst_rate = self._gst_rate(travel_type=travel_type, quote=quote)
        if gst_rate is None:
            return Decimal("0"), Decimal("0"), False, "GST credit is not applied for this booking."

        gst_component = gst_base_amount * gst_rate / (Decimal("1") + gst_rate)
        non_claimable_tax_benefit = gst_component * CORPORATE_TAX_RATE

        if not quote.gst_invoice_available:
            return (
                Decimal("0"),
                non_claimable_tax_benefit,
                False,
                "GST credit not claimed because GST invoice is not available; tax benefit on non-claimable GST applied.",
            )

        if travel_type == TravelType.FLIGHT:
            return (
                gst_component,
                Decimal("0"),
                True,
                "Flight GST credit applied at 5%.",
            )

        if travel_type == TravelType.HOTEL:
            if quote.hotel_state not in HOTEL_GST_REGISTERED_STATES:
                return (
                    Decimal("0"),
                    non_claimable_tax_benefit,
                    False,
                    "Hotel GST credit not claimed because the hotel state is outside company GST registration; tax benefit on non-claimable GST applied.",
                )
            return (
                gst_component,
                Decimal("0"),
                True,
                "Hotel GST credit applied at 18%.",
            )

        return Decimal("0"), Decimal("0"), False, "GST credit is not applied for voucher tracking."

    def _gst_rate(self, *, travel_type: TravelType, quote: QuoteInput) -> Decimal | None:
        if travel_type == TravelType.FLIGHT:
            if not quote.origin_state and not quote.destination_state:
                return None
            if quote.origin_state == "Outside India" and quote.destination_state == "Outside India":
                return None
            return FLIGHT_GST_RATE
        if travel_type == TravelType.HOTEL:
            if not quote.hotel_state:
                return None
            if quote.hotel_state == "Outside India":
                return None
            return HOTEL_GST_RATE
        return None

    def _gst_base_amount(
        self,
        *,
        quote: QuoteInput,
        price_after_discount: Decimal,
        eligible_amount: Decimal,
        cash_component: Decimal,
        voucher_rule: VoucherRule | None,
    ) -> Decimal:
        if voucher_rule is None:
            return price_after_discount
        return eligible_amount + cash_component
