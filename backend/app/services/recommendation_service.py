from datetime import UTC, date, datetime

from app.core.errors import InvalidDecisionError, NotFoundError
from app.data.repositories.audit_ledger import AuditLedger
from app.data.repositories.rules_repository import RulesRepository
from app.domain.enums import TravelType
from app.domain.models import DecisionRecord, QuoteInput, Recommendation
from app.domain.recommendation_engine import RecommendationEngine
from app.services.cap_usage_service import CapUsageService


class RecommendationService:
    def __init__(
        self,
        *,
        rules_repository: RulesRepository | None = None,
        ledger: AuditLedger | None = None,
    ) -> None:
        self.rules_repository = rules_repository or RulesRepository()
        self.ledger = ledger or AuditLedger()
        self.cards = self.rules_repository.cards()
        self.engine = RecommendationEngine(
            cards=self.cards,
            vendors=self.rules_repository.vendors(),
            card_vendor_rules=self.rules_repository.card_vendor_rules(),
            voucher_rules=self.rules_repository.voucher_rules(),
        )
        self.cap_usage = CapUsageService(ledger=self.ledger, cards=self.cards)
        self._pending: dict[str, Recommendation] = {}
        self._decisions: dict[str, DecisionRecord] = {}

    def create_recommendation(
        self,
        *,
        employee_id: str | None,
        travel_type: TravelType,
        quotes: list[QuoteInput],
        travel_date: date | None = None,
    ) -> Recommendation:
        target_date = travel_date or datetime.now(UTC).date()
        recommendation = self.engine.rank(
            employee_id=employee_id,
            travel_type=travel_type,
            quotes=quotes,
            usage_by_card=self.cap_usage.usage_for(target_date),
        )
        self._pending[recommendation.id] = recommendation
        self.ledger.save_recommendation(recommendation)
        return recommendation

    def get_recommendation(self, recommendation_id: str) -> Recommendation:
        recommendation = self._pending.get(recommendation_id)
        if recommendation is None:
            recommendation = self.ledger.get_recommendation(recommendation_id)
        if recommendation is None:
            raise NotFoundError(f"Unknown recommendation: {recommendation_id}")
        self._pending[recommendation.id] = recommendation
        return recommendation

    def record_decision(
        self,
        *,
        recommendation_id: str,
        accepted: bool,
        selected_option_id: str | None = None,
        selected_card_id: str | None = None,
        selected_vendor_id: str | None = None,
        decline_reason: str | None = None,
    ) -> DecisionRecord:
        recommendation = self.get_recommendation(recommendation_id)
        selected_option = None

        if selected_option_id is not None:
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

        if accepted and selected_option is None and not (selected_card_id and selected_vendor_id):
            selected_option = recommendation.ranked_options[0]

        if not accepted and not decline_reason:
            raise InvalidDecisionError("A decline reason is required when the recommendation is declined.")

        decision = DecisionRecord(
            recommendation_id=recommendation_id,
            accepted=accepted,
            selected_option_id=selected_option.id if selected_option else selected_option_id,
            selected_card_id=selected_option.card_id if selected_option else selected_card_id,
            selected_vendor_id=selected_option.vendor_id if selected_option else selected_vendor_id,
            decline_reason=None if accepted else decline_reason,
        )
        self._decisions[recommendation_id] = decision
        self.ledger.append_decision(decision)
        return decision

    def get_decision(self, recommendation_id: str) -> DecisionRecord | None:
        decision = self._decisions.get(recommendation_id)
        if decision is None:
            decision = self.ledger.get_decision(recommendation_id)
        if decision is not None:
            self._decisions[recommendation_id] = decision
        return decision
