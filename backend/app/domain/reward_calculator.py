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
ECONOMY_FLIGHT_GST_RATE = Decimal("0.05")
NON_ECONOMY_FLIGHT_GST_RATE = Decimal("0.18")
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
        (
            gst_rate,
            gst_credit,
            tax_benefit,
            deductible_expense,
            gst_claimable,
            foreign_transaction,
            gst_note,
        ) = self._tax_effects(
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
            gst_rate=gst_rate,
            gst_credit=money(gst_credit),
            tax_benefit=money(tax_benefit),
            deductible_expense=money(deductible_expense),
            foreign_transaction=foreign_transaction,
            gst_claimable=gst_claimable,
            gst_note=gst_note,
            net_cost=money(net_cost),
            cap_remaining_after=points(non_negative(available_bonus_cap - awarded_bonus_points)),
            explanation=(
                f"{card.name} through {vendor.name}: net cost equals price after discount "
                f"minus rupee value of points, GST credit, and the calculated corporate tax benefit. {gst_note} {cap_note}"
            ),
        )

    def _tax_effects(
        self,
        *,
        quote: QuoteInput,
        travel_type: TravelType,
        gst_base_amount: Decimal,
    ) -> tuple[Decimal, Decimal, Decimal, Decimal, bool, bool, str]:
        gst_rate = self._gst_rate(travel_type=travel_type, quote=quote)
        foreign_transaction = self._is_foreign_booking(travel_type=travel_type, quote=quote)

        if travel_type == TravelType.FLIGHT:
            if gst_rate is None:
                return (
                    Decimal("0"), Decimal("0"), Decimal("0"), Decimal("0"), False, foreign_transaction,
                    "GST and tax benefit are not estimated because the required location details are unavailable.",
                )
            eligible_share = self._flight_gst_eligible_share(quote)
            if not quote.gst_invoice_available or eligible_share == 0:
                deductible_expense = gst_base_amount
                reason = (
                    "GST credit is not claimed because an invoice is unavailable"
                    if not quote.gst_invoice_available
                    else "GST credit is not estimated because this itinerary does not begin in India"
                )
                return (
                    gst_rate,
                    Decimal("0"),
                    deductible_expense * CORPORATE_TAX_RATE,
                    deductible_expense,
                    False,
                    foreign_transaction,
                    f"{reason}; the full eligible cost is treated as tax-deductible.",
                )
            gst_component = gst_base_amount * eligible_share * gst_rate / (Decimal("1") + gst_rate)
            deductible_expense = gst_base_amount - gst_component
            effective_rate = gst_rate * eligible_share
            return (
                gst_rate,
                gst_component,
                deductible_expense * CORPORATE_TAX_RATE,
                deductible_expense,
                True,
                foreign_transaction,
                f"Estimated flight GST credit applies to {eligible_share * 100}% of this itinerary at an effective {effective_rate * 100}% rate; the invoice will reconcile the final amount.",
            )

        if foreign_transaction:
            deductible_expense = gst_base_amount
            return (
                Decimal("0"),
                Decimal("0"),
                deductible_expense * CORPORATE_TAX_RATE,
                deductible_expense,
                False,
                True,
                "Foreign business booking: no Indian GST credit; the full eligible cost is treated as tax-deductible.",
            )

        if gst_rate is None:
            return (
                Decimal("0"),
                Decimal("0"),
                Decimal("0"),
                Decimal("0"),
                False,
                False,
                "GST and tax benefit are not estimated because the required location details are unavailable.",
            )

        gst_component = gst_base_amount * gst_rate / (Decimal("1") + gst_rate)

        if not quote.gst_invoice_available:
            deductible_expense = gst_base_amount
            return (
                gst_rate,
                Decimal("0"),
                deductible_expense * CORPORATE_TAX_RATE,
                deductible_expense,
                False,
                False,
                "GST credit is not claimed because an invoice is unavailable; the full eligible cost is treated as tax-deductible.",
            )

        if travel_type == TravelType.HOTEL:
            if quote.hotel_state not in HOTEL_GST_REGISTERED_STATES:
                deductible_expense = gst_base_amount
                return (
                    gst_rate,
                    Decimal("0"),
                    deductible_expense * CORPORATE_TAX_RATE,
                    deductible_expense,
                    False,
                    False,
                    "Hotel GST credit is not claimed because the hotel is outside the company GST registration; the full eligible cost is tax-deductible.",
                )
            deductible_expense = gst_base_amount - gst_component
            return (
                gst_rate,
                gst_component,
                deductible_expense * CORPORATE_TAX_RATE,
                deductible_expense,
                True,
                False,
                "Hotel GST credit applied at 18%; the pre-GST cost is tax-deductible.",
            )

        return (
            Decimal("0"),
            Decimal("0"),
            Decimal("0"),
            Decimal("0"),
            False,
            False,
            "GST credit is not applied for voucher tracking.",
        )

    def _gst_rate(self, *, travel_type: TravelType, quote: QuoteInput) -> Decimal | None:
        if travel_type == TravelType.FLIGHT:
            if not quote.origin_state and not quote.destination_state:
                return None
            if quote.flight_class and quote.flight_class != "Economy":
                return NON_ECONOMY_FLIGHT_GST_RATE
            return ECONOMY_FLIGHT_GST_RATE
        if travel_type == TravelType.HOTEL:
            if not quote.hotel_state:
                return None
            if self._is_foreign_booking(travel_type=travel_type, quote=quote):
                return None
            return HOTEL_GST_RATE
        return None

    def _is_foreign_booking(self, *, travel_type: TravelType, quote: QuoteInput) -> bool:
        if travel_type == TravelType.FLIGHT:
            return quote.origin_state == "Outside India" or quote.destination_state == "Outside India"
        return travel_type == TravelType.HOTEL and quote.hotel_state == "Outside India"

    def _flight_gst_eligible_share(self, quote: QuoteInput) -> Decimal:
        if quote.origin_state == "Outside India":
            return Decimal("0")
        if quote.destination_state != "Outside India":
            return Decimal("1")
        return Decimal("1") / Decimal(max(1, quote.flight_sector_count))

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
