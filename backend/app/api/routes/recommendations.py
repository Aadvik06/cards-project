from fastapi import APIRouter, HTTPException

from app.api.dependencies import (
    get_monthly_log_service,
    get_recommendation_service,
    get_transaction_service,
)
from app.core.errors import OptimizerError
from app.schemas.recommendation import (
    DecisionRequest,
    DecisionResponse,
    FinalizeTransactionRequest,
    RecommendationCreateRequest,
    RecommendationResponse,
    TransactionResponse,
)


router = APIRouter()


@router.post("/recommendations", response_model=RecommendationResponse)
def create_recommendation(payload: RecommendationCreateRequest) -> RecommendationResponse:
    try:
        recommendation = get_recommendation_service().create_recommendation(
            employee_id=payload.employee_id,
            travel_type=payload.travel_type,
            travel_date=payload.travel_date,
            quotes=[quote.to_domain() for quote in payload.quotes],
        )
        return RecommendationResponse.from_domain(recommendation)
    except OptimizerError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/recommendations/{recommendation_id}/decision", response_model=DecisionResponse)
def record_decision(recommendation_id: str, payload: DecisionRequest) -> DecisionResponse:
    try:
        decision = get_recommendation_service().record_decision(
            recommendation_id=recommendation_id,
            accepted=payload.accepted,
            selected_option_id=payload.selected_option_id,
            selected_card_id=payload.selected_card_id,
            selected_vendor_id=payload.selected_vendor_id,
            decline_reason=payload.decline_reason,
        )
        return DecisionResponse.from_domain(decision)
    except OptimizerError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/recommendations/{recommendation_id}/finalize", response_model=TransactionResponse)
def finalize_transaction(
    recommendation_id: str, payload: FinalizeTransactionRequest
) -> TransactionResponse:
    try:
        transaction = get_transaction_service().finalize_transaction(
            recommendation_id=recommendation_id,
            final_amount_paid=payload.final_amount_paid,
            selected_option_id=payload.selected_option_id,
            selected_card_id=payload.selected_card_id,
            selected_vendor_id=payload.selected_vendor_id,
            paid_at=payload.paid_at,
        )
        return TransactionResponse.from_domain(transaction)
    except OptimizerError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/logs/monthly/{year}/{month}")
def get_monthly_log(year: int, month: int) -> dict:
    if month < 1 or month > 12:
        raise HTTPException(status_code=400, detail="Month must be between 1 and 12.")
    return get_monthly_log_service().get_month(year, month)

