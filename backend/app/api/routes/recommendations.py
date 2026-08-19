from fastapi import APIRouter, HTTPException, Request, Response

from app.api.dependencies import (
    get_monthly_log_service,
    get_recommendation_service,
    get_report_service,
    get_transaction_service,
)
from app.core.errors import OptimizerError
from app.schemas.recommendation import (
    DecisionRequest,
    DecisionResponse,
    DraftResponse,
    DraftSaveRequest,
    FinalizeTransactionRequest,
    RecommendationCreateRequest,
    RecommendationResponse,
    TransactionResponse,
    VoucherLogRequest,
)


router = APIRouter()


@router.post("/recommendations", response_model=RecommendationResponse)
def create_recommendation(payload: RecommendationCreateRequest) -> RecommendationResponse:
    try:
        recommendation = get_recommendation_service().create_recommendation(
            employee_id=payload.employee_name or payload.employee_id,
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
    if not payload.details.get("description", "").strip():
        raise HTTPException(status_code=400, detail="Description is required before final logging.")
    try:
        transaction = get_transaction_service().finalize_transaction(
            recommendation_id=recommendation_id,
            final_amount_paid=payload.final_amount_paid,
            selected_option_id=payload.selected_option_id,
            selected_card_id=payload.selected_card_id,
            selected_vendor_id=payload.selected_vendor_id,
            paid_at=payload.paid_at,
            details=payload.details,
        )
        return TransactionResponse.from_domain(transaction)
    except OptimizerError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/vouchers", response_model=TransactionResponse)
def log_voucher_purchase(payload: VoucherLogRequest) -> TransactionResponse:
    if not payload.description.strip():
        raise HTTPException(status_code=400, detail="Description is required for voucher logging.")
    try:
        transaction = get_transaction_service().log_voucher_purchase(
            employee_name=payload.employee_name,
            vendor_name=payload.vendor_name,
            final_amount_paid=payload.final_amount_paid,
            paid_at=payload.paid_at,
            description=payload.description,
        )
        return TransactionResponse.from_domain(transaction)
    except OptimizerError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/transactions")
def get_transactions() -> list[dict]:
    return get_monthly_log_service().get_all_transactions()


@router.delete("/transactions/{transaction_id}")
def delete_transaction(transaction_id: str) -> dict:
    deleted = get_monthly_log_service().delete_transaction(transaction_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Transaction not found.")
    return {"deleted": True, "transaction_id": transaction_id}


@router.get("/drafts", response_model=list[DraftResponse])
def get_drafts() -> list[dict]:
    return get_recommendation_service().ledger.read_drafts()


@router.post("/drafts", response_model=DraftResponse)
def save_draft(payload: DraftSaveRequest, request: Request) -> dict:
    created_by = getattr(request.state, "user_email", None)
    return get_recommendation_service().ledger.save_draft(
        draft_id=payload.id,
        title=payload.title,
        travel_type=payload.travel_type,
        current_step=payload.current_step,
        data=payload.data,
        created_by=created_by,
    )


@router.get("/drafts/{draft_id}", response_model=DraftResponse)
def get_draft(draft_id: str) -> dict:
    draft = get_recommendation_service().ledger.get_draft(draft_id)
    if draft is None:
        raise HTTPException(status_code=404, detail="Draft not found.")
    return draft


@router.delete("/drafts/{draft_id}")
def delete_draft(draft_id: str) -> dict:
    deleted = get_recommendation_service().ledger.delete_draft(draft_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Draft not found.")
    return {"deleted": True, "draft_id": draft_id}


@router.get("/logs/summary")
def get_points_summary() -> dict:
    return get_monthly_log_service().get_summary()


@router.get("/logs/monthly/{year}/{month}")
def get_monthly_log(year: int, month: int) -> dict:
    if month < 1 or month > 12:
        raise HTTPException(status_code=400, detail="Month must be between 1 and 12.")
    return get_monthly_log_service().get_month(year, month)


@router.get("/reports/current-month.pdf")
def current_month_report() -> Response:
    pdf_bytes, filename = get_report_service().current_month_pdf()
    return _pdf_response(pdf_bytes, filename)


@router.get("/reports/monthly/{year}/{month}.pdf")
def monthly_report(year: int, month: int) -> Response:
    if month < 1 or month > 12:
        raise HTTPException(status_code=400, detail="Month must be between 1 and 12.")
    pdf_bytes, filename = get_report_service().month_pdf(year, month)
    return _pdf_response(pdf_bytes, filename)


@router.get("/reports/ytd/{year}.pdf")
def year_to_date_report(year: int) -> Response:
    pdf_bytes, filename = get_report_service().year_to_date_pdf(year)
    return _pdf_response(pdf_bytes, filename)


def _pdf_response(pdf_bytes: bytes, filename: str) -> Response:
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
