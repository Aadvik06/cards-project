from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

from app.core.decimal_math import money, non_negative, points
from app.core.errors import InvalidDecisionError
from app.domain.cap_tracker import remaining_bonus_cap
from app.domain.enums import TravelType
from app.domain.models import QuoteInput, Recommendation, TransactionRecord, UsageSnapshot
from app.domain.recommendation_engine import AGENT_CARD_ID, AGENT_VENDOR_BY_TYPE
from app.services.recommendation_service import RecommendationService


class TransactionService:
    def __init__(self, recommendation_service: RecommendationService) -> None:
        self.recommendation_service = recommendation_service

    def finalize_transaction(
        self,
        *,
        recommendation_id: str,
        final_amount_paid: Decimal,
        selected_option_id: str | None = None,
        selected_card_id: str | None = None,
        selected_vendor_id: str | None = None,
        paid_at: datetime | None = None,
        points_used: Decimal = Decimal("0"),
        details: dict[str, str] | None = None,
    ) -> TransactionRecord:
        recommendation = self.recommendation_service.get_recommendation(recommendation_id)

        if selected_option_id:
            selected_option = next(
                (
                    option
                    for option in recommendation.ranked_options
                    if option.id == selected_option_id
                ),
                None,
            )
            if selected_option is None:
                raise InvalidDecisionError("Selected option does not belong to this recommendation.")
            selected_card_id = selected_option.card_id
            selected_vendor_id = selected_option.vendor_id

        decision = self.recommendation_service.get_decision(recommendation_id)
        if not selected_card_id and decision and decision.selected_card_id:
            selected_card_id = decision.selected_card_id
        if not selected_vendor_id and decision and decision.selected_vendor_id:
            selected_vendor_id = decision.selected_vendor_id

        if not selected_card_id or not selected_vendor_id:
            raise InvalidDecisionError("Final card and vendor are required before logging a transaction.")

        original_option = next(
            (
                option
                for option in recommendation.ranked_options
                if option.card_id == selected_card_id and option.vendor_id == selected_vendor_id
            ),
            None,
        )
        if original_option is None:
            raise InvalidDecisionError("Final card/vendor pair was not eligible in the recommendation.")

        paid_at = paid_at or datetime.now(UTC)
        original_quote = self._original_quote(recommendation, selected_vendor_id)
        if selected_vendor_id == AGENT_VENDOR_BY_TYPE.get(recommendation.travel_type):
            if points_used:
                raise InvalidDecisionError("Reward-point redemption is not available for Travel Agent bookings.")
            (
                gst_rate,
                gst_credit,
                tax_benefit,
                deductible_expense,
                _,
                foreign_transaction,
                _,
            ) = self.recommendation_service.engine.calculator._tax_effects(
                quote=original_quote,
                travel_type=recommendation.travel_type,
                gst_base_amount=final_amount_paid,
            )
            if selected_card_id == AGENT_CARD_ID:
                base_points = points(Decimal("0"))
                points_value_rupees = money(Decimal("0"))
            else:
                card = next(
                    (item for item in self.recommendation_service.cards if item.id == selected_card_id),
                    None,
                )
                if card is None:
                    raise InvalidDecisionError("Selected card is not available for the Travel Agent booking.")
                base_points = points(final_amount_paid * card.base_rate)
                points_value_rupees = money(base_points * card.point_value_rupees)
            transaction = TransactionRecord(
                id=str(uuid4()),
                recommendation_id=recommendation_id,
                employee_id=recommendation.employee_id,
                travel_type=recommendation.travel_type,
                card_id=selected_card_id,
                vendor_id=selected_vendor_id,
                final_amount_paid=money(final_amount_paid),
                discount_rate=Decimal("0"),
                base_points=base_points,
                bonus_points=points(Decimal("0")),
                total_points=base_points,
                points_value_rupees=points_value_rupees,
                points_used=points(Decimal("0")),
                gst_rate=gst_rate,
                gst_credit=money(gst_credit),
                tax_benefit=money(tax_benefit),
                deductible_expense=money(deductible_expense),
                foreign_transaction=foreign_transaction,
                net_cost=money(final_amount_paid - points_value_rupees - gst_credit - tax_benefit),
                paid_at=paid_at,
                details=details or {},
            )
            self.recommendation_service.ledger.append_transaction(transaction)
            return transaction

        card = next(card for card in self.recommendation_service.cards if card.id == selected_card_id)
        if points_used and selected_card_id not in {"hdfc_infinia", "icici_times_black"}:
            raise InvalidDecisionError("Reward-point redemption can only be recorded for HDFC Infinia or ICICI Times Black.")
        point_redemption_value = points_used * card.point_value_rupees
        if point_redemption_value > final_amount_paid:
            raise InvalidDecisionError("Reward points used cannot exceed the final booking amount.")

        if self._is_amex_voucher_vendor(selected_card_id, selected_vendor_id, details or {}):
            transaction = self._finalize_amex_voucher_split(
                recommendation=recommendation,
                selected_card_id=selected_card_id,
                selected_vendor_id=selected_vendor_id,
                final_amount_paid=final_amount_paid,
                discount_rate=original_option.discount_rate,
                paid_at=paid_at,
                details=details or {},
                original_quote=original_quote,
            )
            self.recommendation_service.ledger.append_transaction(transaction)
            return transaction

        final_quote = QuoteInput(
            vendor_id=selected_vendor_id,
            amount=final_amount_paid - point_redemption_value,
            discount_rate=original_option.discount_rate,
            gst_invoice_available=original_quote.gst_invoice_available,
            origin_state=original_quote.origin_state,
            destination_state=original_quote.destination_state,
            hotel_state=original_quote.hotel_state,
            flight_class=original_quote.flight_class,
            flight_sector_count=original_quote.flight_sector_count,
        )
        final_recommendation = self.recommendation_service.engine.rank(
            employee_id=recommendation.employee_id,
            travel_type=recommendation.travel_type,
            quotes=[final_quote],
            usage_by_card=self.recommendation_service.cap_usage.usage_for(paid_at.date()),
        )
        final_option = next(
            option
            for option in final_recommendation.ranked_options
            if option.card_id == selected_card_id and option.vendor_id == selected_vendor_id
        )
        tax_quote = QuoteInput(
            vendor_id=selected_vendor_id,
            amount=final_amount_paid,
            gst_invoice_available=original_quote.gst_invoice_available,
            origin_state=original_quote.origin_state,
            destination_state=original_quote.destination_state,
            hotel_state=original_quote.hotel_state,
            flight_class=original_quote.flight_class,
            flight_sector_count=original_quote.flight_sector_count,
        )
        (
            gst_rate,
            gst_credit,
            tax_benefit,
            deductible_expense,
            _,
            foreign_transaction,
            _,
        ) = self.recommendation_service.engine.calculator._tax_effects(
            quote=tax_quote,
            travel_type=recommendation.travel_type,
            gst_base_amount=final_amount_paid,
        )

        transaction = TransactionRecord(
            id=str(uuid4()),
            recommendation_id=recommendation_id,
            employee_id=recommendation.employee_id,
            travel_type=recommendation.travel_type,
            card_id=selected_card_id,
            vendor_id=selected_vendor_id,
            final_amount_paid=final_option.listed_amount,
            discount_rate=final_option.discount_rate,
            base_points=final_option.base_points,
            bonus_points=final_option.awarded_bonus_points,
            total_points=final_option.total_points,
            points_value_rupees=final_option.points_value_rupees,
            points_used=points(points_used),
            gst_rate=gst_rate,
            gst_credit=money(gst_credit),
            tax_benefit=money(tax_benefit),
            deductible_expense=money(deductible_expense),
            foreign_transaction=foreign_transaction,
            net_cost=money(final_amount_paid - point_redemption_value - final_option.points_value_rupees - gst_credit - tax_benefit),
            paid_at=paid_at,
            details=details or {},
        )
        self.recommendation_service.ledger.append_transaction(transaction)
        return transaction

    def _is_amex_voucher_vendor(self, card_id: str, vendor_id: str, details: dict) -> bool:
        if card_id != "amex":
            return False
        if (
            "voucher_purchase_amount_paid" not in details
            and "card_balance_paid" not in details
            and "voucher_amount_paid" not in details
            and "cash_amount_paid" not in details
        ):
            return False
        return ("amex", vendor_id) in self.recommendation_service.engine.voucher_rules

    def _original_quote(self, recommendation: Recommendation, vendor_id: str) -> QuoteInput:
        for quote in recommendation.quotes:
            if quote.vendor_id == vendor_id:
                return quote
        return QuoteInput(vendor_id=vendor_id, amount=Decimal("0"))

    def _finalize_amex_voucher_split(
        self,
        *,
        recommendation: Recommendation,
        selected_card_id: str,
        selected_vendor_id: str,
        final_amount_paid: Decimal,
        discount_rate: Decimal,
        paid_at: datetime,
        details: dict,
        original_quote: QuoteInput,
    ) -> TransactionRecord:
        card = next(card for card in self.recommendation_service.cards if card.id == selected_card_id)
        voucher_face_value = money(Decimal(str(details.get("voucher_face_value_used") or details.get("voucher_amount_paid") or "0")))
        voucher_purchase_amount = money(
            Decimal(str(details.get("voucher_purchase_amount_paid") or details.get("voucher_amount_paid") or "0"))
        )
        card_balance = money(Decimal(str(details.get("card_balance_paid") or details.get("cash_amount_paid") or "0")))
        checkout_value = money(voucher_face_value + card_balance)
        split_total = money(voucher_purchase_amount + card_balance)
        if split_total != money(final_amount_paid):
            raise InvalidDecisionError("Voucher purchase cost and direct card balance must add up to the final amount paid.")

        if "checkout_value" not in details:
            details["checkout_value"] = str(checkout_value)

        usage = self.recommendation_service.cap_usage.usage_for(paid_at.date()).get(
            card.id,
            UsageSnapshot(),
        )
        base_points = split_total * card.base_rate
        voucher_base_points = voucher_purchase_amount * card.base_rate
        raw_bonus_points = non_negative((voucher_base_points * card.multiplier_for(recommendation.travel_type)) - voucher_base_points)
        awarded_bonus_points = min(raw_bonus_points, remaining_bonus_cap(card, usage))
        total_points = base_points + awarded_bonus_points
        points_value_rupees = total_points * card.point_value_rupees
        gst_quote = QuoteInput(
            vendor_id=selected_vendor_id,
            amount=checkout_value,
            gst_invoice_available=original_quote.gst_invoice_available,
            origin_state=original_quote.origin_state,
            destination_state=original_quote.destination_state,
            hotel_state=original_quote.hotel_state,
            flight_class=original_quote.flight_class,
            flight_sector_count=original_quote.flight_sector_count,
        )
        (
            gst_rate,
            gst_credit,
            tax_benefit,
            deductible_expense,
            _,
            foreign_transaction,
            _,
        ) = self.recommendation_service.engine.calculator._tax_effects(
            quote=gst_quote,
            travel_type=recommendation.travel_type,
            gst_base_amount=checkout_value,
        )

        return TransactionRecord(
            id=str(uuid4()),
            recommendation_id=recommendation.id,
            employee_id=recommendation.employee_id,
            travel_type=recommendation.travel_type,
            card_id=selected_card_id,
            vendor_id=selected_vendor_id,
            final_amount_paid=split_total,
            discount_rate=discount_rate,
            base_points=points(base_points),
            bonus_points=points(awarded_bonus_points),
            total_points=points(total_points),
            points_value_rupees=money(points_value_rupees),
            points_used=points(Decimal("0")),
            gst_rate=gst_rate,
            gst_credit=money(gst_credit),
            tax_benefit=money(tax_benefit),
            deductible_expense=money(deductible_expense),
            foreign_transaction=foreign_transaction,
            net_cost=money(split_total - points_value_rupees - gst_credit - tax_benefit),
            paid_at=paid_at,
            details=details,
        )

    def log_voucher_purchase(
        self,
        *,
        employee_name: str | None,
        card_id: str = "amex",
        vendor_name: str,
        final_amount_paid: Decimal,
        paid_at: datetime | None = None,
        description: str,
    ) -> TransactionRecord:
        paid_at = paid_at or datetime.now(UTC)
        if card_id not in {"amex", "hdfc_infinia", "icici_times_black"}:
            raise OptimizerError("Voucher purchases can only use American Express, HDFC Infinia, or ICICI Times Black.")
        card = next(card for card in self.recommendation_service.cards if card.id == card_id)
        usage = self.recommendation_service.cap_usage.usage_for(paid_at.date()).get(
            card.id,
            UsageSnapshot(),
        )
        multiplier = card.flight_multiplier if card_id in {"hdfc_infinia", "icici_times_black"} else card.hotel_multiplier
        base_points = final_amount_paid * card.base_rate
        raw_bonus_points = (base_points * multiplier) - base_points
        awarded_bonus_points = min(raw_bonus_points, remaining_bonus_cap(card, usage))
        total_points = base_points + awarded_bonus_points
        points_value_rupees = total_points * card.point_value_rupees
        voucher_id = f"voucher-{uuid4()}"
        voucher_vendor_id = {
            "amex": "amex_other_voucher",
            "hdfc_infinia": "hdfc_smartbuy_voucher",
            "icici_times_black": "icici_ishop_voucher",
        }[card_id]

        self.recommendation_service.ledger.save_recommendation(
            Recommendation(
                id=voucher_id,
                employee_id=employee_name,
                travel_type=TravelType.VOUCHER,
                quotes=[
                    QuoteInput(
                        vendor_id=voucher_vendor_id,
                        amount=final_amount_paid,
                        merchant_name=vendor_name,
                        description=description,
                    )
                ],
                ranked_options=[],
                card_rankings=[],
                created_at=paid_at,
            )
        )

        transaction = TransactionRecord(
            id=str(uuid4()),
            recommendation_id=voucher_id,
            employee_id=employee_name,
            travel_type=TravelType.VOUCHER,
            card_id=card_id,
            vendor_id=voucher_vendor_id,
            discount_rate=Decimal("0"),
            final_amount_paid=money(final_amount_paid),
            base_points=points(base_points),
            bonus_points=points(awarded_bonus_points),
            total_points=points(total_points),
            points_value_rupees=money(points_value_rupees),
            points_used=points(Decimal("0")),
            gst_rate=Decimal("0"),
            gst_credit=money(Decimal("0")),
            tax_benefit=money(Decimal("0")),
            deductible_expense=money(Decimal("0")),
            foreign_transaction=False,
            net_cost=money(final_amount_paid - points_value_rupees),
            paid_at=paid_at,
            details={
                "vendor_name": vendor_name,
                "description": description,
                "purchase_channel": {
                    "amex": "American Express",
                    "hdfc_infinia": "HDFC SmartBuy",
                    "icici_times_black": "ICICI iShop",
                }[card_id],
            },
        )
        self.recommendation_service.ledger.append_transaction(transaction)
        return transaction
