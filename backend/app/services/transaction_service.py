from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

from app.core.decimal_math import money, non_negative, points
from app.core.errors import InvalidDecisionError
from app.domain.cap_tracker import remaining_bonus_cap
from app.domain.enums import TravelType
from app.domain.models import QuoteInput, Recommendation, TransactionRecord, UsageSnapshot
from app.domain.recommendation_engine import AGENT_CARD_ID
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
        if selected_card_id == AGENT_CARD_ID:
            transaction = TransactionRecord(
                id=str(uuid4()),
                recommendation_id=recommendation_id,
                employee_id=recommendation.employee_id,
                travel_type=recommendation.travel_type,
                card_id=selected_card_id,
                vendor_id=selected_vendor_id,
                final_amount_paid=money(final_amount_paid),
                discount_rate=Decimal("0"),
                base_points=points(Decimal("0")),
                bonus_points=points(Decimal("0")),
                total_points=points(Decimal("0")),
                points_value_rupees=money(Decimal("0")),
                net_cost=money(final_amount_paid),
                paid_at=paid_at,
                details=details or {},
            )
            self.recommendation_service.ledger.append_transaction(transaction)
            return transaction

        if self._is_amex_voucher_vendor(selected_card_id, selected_vendor_id, details or {}):
            transaction = self._finalize_amex_voucher_split(
                recommendation=recommendation,
                selected_card_id=selected_card_id,
                selected_vendor_id=selected_vendor_id,
                final_amount_paid=final_amount_paid,
                discount_rate=original_option.discount_rate,
                paid_at=paid_at,
                details=details or {},
            )
            self.recommendation_service.ledger.append_transaction(transaction)
            return transaction

        final_quote = QuoteInput(
            vendor_id=selected_vendor_id,
            amount=final_amount_paid,
            discount_rate=original_option.discount_rate,
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
            net_cost=final_option.net_cost,
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
            net_cost=money(split_total - points_value_rupees),
            paid_at=paid_at,
            details=details,
        )

    def log_voucher_purchase(
        self,
        *,
        employee_name: str | None,
        vendor_name: str,
        final_amount_paid: Decimal,
        paid_at: datetime | None = None,
        description: str,
    ) -> TransactionRecord:
        paid_at = paid_at or datetime.now(UTC)
        amex = next(card for card in self.recommendation_service.cards if card.id == "amex")
        usage = self.recommendation_service.cap_usage.usage_for(paid_at.date()).get(
            amex.id,
            UsageSnapshot(),
        )
        base_points = final_amount_paid * amex.base_rate
        raw_bonus_points = (base_points * amex.hotel_multiplier) - base_points
        awarded_bonus_points = min(raw_bonus_points, remaining_bonus_cap(amex, usage))
        total_points = base_points + awarded_bonus_points
        points_value_rupees = total_points * amex.point_value_rupees
        voucher_id = f"voucher-{uuid4()}"

        self.recommendation_service.ledger.save_recommendation(
            Recommendation(
                id=voucher_id,
                employee_id=employee_name,
                travel_type=TravelType.VOUCHER,
                quotes=[
                    QuoteInput(
                        vendor_id="amex_other_voucher",
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
            card_id="amex",
            vendor_id="amex_other_voucher",
            discount_rate=Decimal("0"),
            final_amount_paid=money(final_amount_paid),
            base_points=points(base_points),
            bonus_points=points(awarded_bonus_points),
            total_points=points(total_points),
            points_value_rupees=money(points_value_rupees),
            net_cost=money(final_amount_paid - points_value_rupees),
            paid_at=paid_at,
            details={"vendor_name": vendor_name, "description": description},
        )
        self.recommendation_service.ledger.append_transaction(transaction)
        return transaction
