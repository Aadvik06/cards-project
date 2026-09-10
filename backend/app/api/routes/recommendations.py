import os
import secrets
from uuid import uuid4

from fastapi import APIRouter, File, HTTPException, Request, Response, UploadFile
from fastapi.responses import RedirectResponse

from app.api.dependencies import (
    get_monthly_log_service,
    get_recommendation_service,
    get_report_service,
    get_transaction_service,
)
from app.core.errors import OptimizerError
from app.data.repositories.audit_ledger import InvoiceStorageLimitError
from app.services.supabase_invoice_storage import InvoiceStorageError, SupabaseInvoiceStorage
from app.schemas.recommendation import (
    DecisionRequest,
    DecisionResponse,
    DraftResponse,
    DraftSaveRequest,
    FinalizeTransactionRequest,
    InvoiceUploadCompleteRequest,
    InvoiceUploadRequest,
    RecommendationCreateRequest,
    RecommendationResponse,
    TransactionDetailsUpdateRequest,
    TransactionResponse,
    VoucherLogRequest,
)


router = APIRouter()
# Vercel Functions reject request bodies above 4.5 MB. Leave headroom for the
# multipart form wrapper so every invoice accepted by the page reaches FastAPI.
MAX_INVOICE_SIZE_BYTES = 4 * 1024 * 1024
MAX_CLOUD_INVOICE_SIZE_BYTES = 50 * 1024 * 1024
INVOICE_ARCHIVE_ALLOCATION_BYTES = 400 * 1024 * 1024
ALLOWED_INVOICE_TYPES = {"application/pdf", "image/jpeg", "image/png", "image/webp"}
EDITABLE_TRANSACTION_DETAIL_FIELDS = {
    "flight": {
        "from", "to", "airline", "flight_date", "return_flight_date", "trip_type",
        "outbound_departure_time", "outbound_arrival_time", "return_departure_time",
        "return_arrival_time", "description",
    },
    "hotel": {"hotel_name", "city", "hotel_state", "check_in", "check_out", "description"},
    "voucher": {"vendor_name", "purchase_date", "description"},
}


@router.get("/internal/keepalive", include_in_schema=False)
def keepalive(request: Request) -> dict:
    """Keep the Free-plan database active when invoked by Vercel Cron."""
    cron_secret = os.environ.get("CRON_SECRET")
    authorization = request.headers.get("authorization", "")
    if not cron_secret or not secrets.compare_digest(authorization, f"Bearer {cron_secret}"):
        raise HTTPException(status_code=401, detail="Unauthorized")
    get_monthly_log_service().ledger.keepalive()
    return {"ok": True}


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
            points_used=payload.points_used,
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


@router.get("/invoices/storage-summary")
def get_invoice_storage_summary() -> dict:
    return get_monthly_log_service().ledger.invoice_storage_summary(INVOICE_ARCHIVE_ALLOCATION_BYTES)


@router.get("/invoices")
def get_invoices() -> list[dict]:
    return get_monthly_log_service().ledger.read_invoices()


@router.delete("/transactions/{transaction_id}")
def delete_transaction(transaction_id: str) -> dict:
    deleted = get_monthly_log_service().delete_transaction(transaction_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Transaction not found.")
    return {"deleted": True, "transaction_id": transaction_id}


@router.put("/transactions/{transaction_id}/details")
def update_transaction_details(
    transaction_id: str, payload: TransactionDetailsUpdateRequest
) -> dict:
    ledger = get_monthly_log_service().ledger
    transaction = next((item for item in ledger.read_transactions() if item["id"] == transaction_id), None)
    if transaction is None:
        raise HTTPException(status_code=404, detail="Transaction not found.")
    allowed_fields = EDITABLE_TRANSACTION_DETAIL_FIELDS.get(transaction["travel_type"], set())
    unknown_fields = set(payload.details) - allowed_fields
    if unknown_fields:
        raise HTTPException(status_code=400, detail="Only booking details can be edited. Amounts and calculations are locked.")
    ledger.update_transaction_details(transaction_id, payload.details)
    return {"updated": True, "transaction_id": transaction_id}


@router.post("/transactions/{transaction_id}/invoice")
async def upload_invoice(transaction_id: str, invoice: UploadFile = File(...)) -> dict:
    if invoice.content_type not in ALLOWED_INVOICE_TYPES:
        raise HTTPException(status_code=400, detail="Upload a PDF, JPG, PNG, or WEBP invoice.")
    content = await invoice.read(MAX_INVOICE_SIZE_BYTES + 1)
    if not content:
        raise HTTPException(status_code=400, detail="The invoice file is empty.")
    if len(content) > MAX_INVOICE_SIZE_BYTES:
        raise HTTPException(status_code=400, detail="Invoice files must be 4 MB or smaller.")
    try:
        return get_monthly_log_service().ledger.save_invoice(
            transaction_id=transaction_id,
            filename=invoice.filename or "invoice",
            content_type=invoice.content_type,
            content=content,
            allocation_bytes=INVOICE_ARCHIVE_ALLOCATION_BYTES,
        )
    except InvoiceStorageLimitError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/transactions/{transaction_id}/invoice/upload-url")
def create_invoice_upload_url(transaction_id: str, payload: InvoiceUploadRequest) -> dict:
    if payload.content_type not in ALLOWED_INVOICE_TYPES:
        raise HTTPException(status_code=400, detail="Upload a PDF, JPG, PNG, or WEBP invoice.")
    if payload.file_size_bytes > MAX_CLOUD_INVOICE_SIZE_BYTES:
        raise HTTPException(status_code=400, detail="Invoice files must be 50 MB or smaller.")
    transaction = next((item for item in get_monthly_log_service().ledger.read_transactions() if item["id"] == transaction_id), None)
    if transaction is None:
        raise HTTPException(status_code=404, detail="Transaction not found.")
    extension = os.path.splitext(payload.filename)[1].lower()
    storage_path = f"invoices/{transaction_id}/{uuid4()}{extension}"
    try:
        token = SupabaseInvoiceStorage().create_upload_token(storage_path)
    except InvoiceStorageError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {"bucket": "travel-invoices", "storage_path": storage_path, "token": token}


@router.post("/transactions/{transaction_id}/invoice/complete")
def complete_invoice_upload(transaction_id: str, payload: InvoiceUploadCompleteRequest) -> dict:
    expected_prefix = f"invoices/{transaction_id}/"
    if not payload.storage_path.startswith(expected_prefix):
        raise HTTPException(status_code=400, detail="Invalid invoice upload path.")
    if payload.content_type not in ALLOWED_INVOICE_TYPES:
        raise HTTPException(status_code=400, detail="Upload a PDF, JPG, PNG, or WEBP invoice.")
    try:
        return get_monthly_log_service().ledger.save_cloud_invoice(
            transaction_id=transaction_id,
            filename=payload.filename,
            content_type=payload.content_type,
            storage_path=payload.storage_path,
            file_size_bytes=payload.file_size_bytes,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/transactions/{transaction_id}/invoice")
def get_invoice(transaction_id: str) -> Response:
    invoice = get_monthly_log_service().ledger.get_invoice(transaction_id)
    if invoice is None:
        raise HTTPException(status_code=404, detail="No invoice has been uploaded for this transaction.")
    if invoice.get("storage_path"):
        try:
            url = SupabaseInvoiceStorage().signed_download_url(invoice["storage_path"], invoice["filename"])
        except InvoiceStorageError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        return RedirectResponse(url=url, status_code=307)
    filename = invoice["filename"].replace('"', "")
    return Response(
        content=invoice["file_data"],
        media_type=invoice["content_type"],
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )


@router.delete("/transactions/{transaction_id}/invoice")
def delete_invoice(transaction_id: str) -> dict:
    invoice = get_monthly_log_service().ledger.get_invoice(transaction_id)
    if invoice and invoice.get("storage_path"):
        try:
            SupabaseInvoiceStorage().delete(invoice["storage_path"])
        except InvoiceStorageError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
    deleted = get_monthly_log_service().ledger.delete_invoice(transaction_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="No invoice has been uploaded for this transaction.")
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
