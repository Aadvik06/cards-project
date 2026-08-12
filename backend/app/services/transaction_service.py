from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

from app.core.errors import InvalidDecisionError
from app.domain.models import QuoteInput, TransactionRecord
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
        )
        self.recommendation_service.ledger.append_transaction(transaction)
        return transaction

