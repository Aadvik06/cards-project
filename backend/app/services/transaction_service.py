from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

from app.core.decimal_math import money, points
from app.core.errors import InvalidDecisionError
from app.domain.cap_tracker import remaining_bonus_cap
from app.domain.enums import TravelType
from app.domain.models import QuoteInput, Recommendation, TransactionRecord, UsageSnapshot
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
