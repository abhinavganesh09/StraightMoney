"""
main.py â€” StraightMoney FastAPI application entry point.

Exposes 12 REST endpoints covering campaigns, donations, invoices (with
AI-assisted extraction + policy + advisory checks), human verification,
payout triggering, and the public ledger.
"""

from __future__ import annotations

import asyncio
import json
import math
import os
import shutil
import uuid
from pathlib import Path
from typing import Optional

from fastapi import (
    APIRouter,
    Depends,
    FastAPI,
    File,
    Form,
    HTTPException,
    UploadFile,
    status,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

import audit
import advisory as advisory_module
import extraction as extraction_module
from config import settings
from db import get_db, init_db
from models import (
    PayoutInstallment,
    BudgetLine,
    Campaign,
    Check,
    Donation,
    Invoice,
    Payout,
    Vendor,
    Verification,
)
from payments import PayPalClient, PayPalError
from installments import pay_available, pay_campaign
from policy import run_policy_checks
from schemas import (
    AdvisoryResult,
    CampaignCreate,
    CampaignDetail,
    CampaignOut,
    DonationCaptureOut,
    DonationCreate,
    DonationOut,
    ExtractionResult,
    InvoiceDetail,
    InvoiceOut,
    LedgerEntry,
    VerificationCreate,
    VerificationOut,
)
from seed import seed_demo_data

# ---------------------------------------------------------------------------
# App bootstrap
# ---------------------------------------------------------------------------

app = FastAPI(
    title="StraightMoney API",
    version="1.0.0",
    description="Transparent fundraising with AI-assisted invoice verification.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url, "http://localhost:3000", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


os.makedirs(settings.upload_dir, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=settings.upload_dir), name="uploads")

router = APIRouter()


@app.get("/", tags=["Info"])
@app.get("/api", tags=["Info"])
def root_info():
    """Root info endpoint â€” ensures visiting http://localhost:8000/ never shows 404."""
    return {
        "app": "StraightMoney API",
        "description": "Community fundraising where the organizer never holds the money (PayPal AI Hackathon)",
        "status": "online",
        "version": "1.0.0",
        "docs_url": "/docs",
        "endpoints": {
            "campaigns": "/campaigns",
            "campaign_detail": "/campaigns/1",
            "invoices": "/invoices",
            "ledger": "/campaigns/1/ledger",
            "swagger_docs": "/docs",
            "redoc_docs": "/redoc",
        },
    }


@app.get("/health", tags=["Info"])
@app.get("/api/health", tags=["Info"])
def health_check():
    return {"status": "ok", "app": "StraightMoney"}


@app.on_event("startup")
async def on_startup() -> None:
    """Initialise the database and seed demo data on first boot."""
    init_db()
    db = next(get_db())
    try:
        seed_demo_data(db)
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

paypal = PayPalClient()

_ALLOWED_MIME_TYPES = {
    "application/pdf",
    "image/jpeg",
    "image/jpg",
    "image/png",
    "image/webp",
}


def _invoice_to_detail(inv: Invoice) -> InvoiceDetail:
    return InvoiceDetail.model_validate(inv)


def _guard_invoice_status(inv: Invoice, required: str) -> None:
    if inv.status != required:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Invoice is in status '{inv.status}', expected '{required}'.",
        )


def _get_or_404(db: Session, model, entity_id: int):
    obj = db.get(model, entity_id)
    if obj is None:
        raise HTTPException(status_code=404, detail=f"{model.__name__} {entity_id} not found.")
    return obj


# ---------------------------------------------------------------------------
# Endpoint 1 â€” Create campaign
# ---------------------------------------------------------------------------


@router.post("/campaigns", response_model=CampaignDetail, status_code=201)
def create_campaign(payload: CampaignCreate, db: Session = Depends(get_db)):
    """Create a new fundraising campaign with optional vendors and budget lines."""
    campaign = Campaign(
        title=payload.title,
        description=payload.description,
        goal_amount=payload.goal_amount,
        currency=payload.currency,
        organizer_name=payload.organizer_name,
        status="active",
        pool_balance=0.0,
    )
    db.add(campaign)
    db.flush()

    vendor_by_email: dict[str, Vendor] = {}
    for idx, v in enumerate(payload.vendors):
        vendor = Vendor(
            campaign_id=campaign.id,
            name=v.name,
            payout_email=v.payout_email,
        )
        db.add(vendor)
        db.flush()
        vendor_by_email[v.payout_email.strip().lower()] = vendor

    for bl in payload.budget_lines:
        vendor_id = bl.vendor_id
        if not vendor_id and bl.vendor_name and bl.vendor_payout_email:
            email_key = bl.vendor_payout_email.strip().lower()
            if email_key not in vendor_by_email:
                new_vendor = Vendor(
                    campaign_id=campaign.id,
                    name=bl.vendor_name.strip(),
                    payout_email=bl.vendor_payout_email.strip(),
                )
                db.add(new_vendor)
                db.flush()
                vendor_by_email[email_key] = new_vendor
            vendor_id = vendor_by_email[email_key].id

        budget_line = BudgetLine(
            campaign_id=campaign.id,
            name=bl.name,
            vendor_id=vendor_id,
            budgeted_amount=bl.budgeted_amount,
        )
        db.add(budget_line)

    db.commit()
    db.refresh(campaign)
    audit.log(db, actor="system", action="campaign.created", campaign_id=campaign.id)
    return CampaignDetail.model_validate(campaign)


# ---------------------------------------------------------------------------
# Endpoint 2 â€” Get campaign detail
# ---------------------------------------------------------------------------


@router.get("/campaigns/{campaign_id}", response_model=CampaignDetail)
def get_campaign(campaign_id: int, db: Session = Depends(get_db)):
    """Retrieve full campaign detail including vendors and budget lines."""
    campaign = _get_or_404(db, Campaign, campaign_id)
    return CampaignDetail.model_validate(campaign)


# ---------------------------------------------------------------------------
# Endpoint 3 â€” List campaigns
# ---------------------------------------------------------------------------


@router.get("/campaigns", response_model=list[CampaignOut])
def list_campaigns(db: Session = Depends(get_db)):
    """Return a summary list of all campaigns."""
    campaigns = db.query(Campaign).order_by(Campaign.created_at.desc()).all()
    return [CampaignOut.model_validate(c) for c in campaigns]


# ---------------------------------------------------------------------------
# Endpoint 4 â€” Create donation (PayPal order)
# ---------------------------------------------------------------------------


@router.post("/campaigns/{campaign_id}/donate", response_model=DonationOut, status_code=201)
@router.post("/campaigns/{campaign_id}/donations", response_model=DonationOut, status_code=201)
async def create_donation(
    campaign_id: int,
    payload: DonationCreate,
    db: Session = Depends(get_db),
):
    """
    Initiate a PayPal order for a campaign donation.

    The frontend should redirect the donor to the PayPal approval URL returned
    in the ``paypal_order`` field of the response, then call the capture
    endpoint once the donor approves.
    """
    campaign = _get_or_404(db, Campaign, campaign_id)
    if campaign.status != "active":
        raise HTTPException(status_code=400, detail="Donations are only accepted for active campaigns.")

    if payload.simulate or not paypal.is_configured:
        order_id = f"SANDBOX-SIM-ORDER-{uuid.uuid4().hex[:10].upper()}"
        is_simulated = True
    else:
        try:
            order = await paypal.create_order(
                campaign_id=campaign_id,
                amount=payload.amount,
                currency=campaign.currency,
                donor_name=payload.donor_name,
            )
            order_id = order["id"]
            is_simulated = False
        except PayPalError as exc:
            raise HTTPException(status_code=502, detail=f"PayPal error: {exc.body}")

    donation = Donation(
        campaign_id=campaign_id,
        donor_name=payload.donor_name,
        amount=payload.amount,
        currency=campaign.currency,
        paypal_order_id=order_id,
        status="created",
    )
    db.add(donation)
    db.commit()
    db.refresh(donation)
    audit.log(
        db,
        actor=payload.donor_name,
        action="donation.created",
        campaign_id=campaign_id,
        detail={"paypal_order_id": order_id, "amount": payload.amount, "simulated": is_simulated},
    )
    return DonationOut.model_validate(donation)


# ---------------------------------------------------------------------------
# Endpoint 5 â€” Capture donation
# ---------------------------------------------------------------------------


@router.post("/donations/{order_id}/capture", response_model=DonationCaptureOut)
async def capture_donation(order_id: str, db: Session = Depends(get_db)):
    """
    Capture an approved PayPal order and credit the campaign pool.

    ``order_id`` is the PayPal order ID (returned by the create-donation
    endpoint).  Call this after the donor has approved payment on PayPal.
    """
    donation = db.query(Donation).filter_by(paypal_order_id=order_id).first()
    if donation is None:
        raise HTTPException(status_code=404, detail=f"Donation with PayPal order '{order_id}' not found.")
    if donation.status == "captured":
        raise HTTPException(status_code=409, detail="Donation already captured.")

    if not paypal.is_configured or order_id.startswith("SANDBOX-"):
        capture_data = {
            "id": order_id,
            "status": "COMPLETED",
            "simulated": True,
        }
    else:
        try:
            capture_data = await paypal.capture_order(order_id)
        except PayPalError as exc:
            body_str = json.dumps(exc.body) if isinstance(exc.body, (dict, list)) else str(exc.body)
            if "ORDER_NOT_APPROVED" in body_str:
                import asyncio
                await asyncio.sleep(1.0)
                try:
                    capture_data = await paypal.capture_order(order_id)
                except PayPalError:
                    raise HTTPException(
                        status_code=400,
                        detail=(
                            "PayPal order was not approved in the checkout window. Please log in with a PayPal "
                            "Sandbox Personal/Buyer test account in the popup and click 'Pay Now', or click "
                            "'Simulate sandbox donation without popup' to complete a test donation instantly."
                        ),
                    )
            else:
                raise HTTPException(status_code=502, detail=f"PayPal error: {exc.body}")

    donation.status = "captured"
    campaign = db.get(Campaign, donation.campaign_id)
    if campaign:
        campaign.pool_balance += donation.amount

    db.commit()
    db.refresh(donation)
    audit.log(
        db,
        actor=donation.donor_name,
        action="donation.captured",
        campaign_id=donation.campaign_id,
        detail={"amount": donation.amount, "new_pool_balance": campaign.pool_balance if campaign else None},
    )
    if campaign:
        await pay_campaign(db, campaign.id, paypal)
    return DonationCaptureOut(
        **DonationOut.model_validate(donation).model_dump(),
        paypal_capture_details=capture_data,
    )


# ---------------------------------------------------------------------------
# Endpoint 6 â€” Submit invoice  (POST /invoices)
# ---------------------------------------------------------------------------


@router.post("/invoices", response_model=InvoiceDetail, status_code=201)
async def submit_invoice(
    campaign_id: int = Form(...),
    budget_line_id: int = Form(...),
    invoice_number: str = Form(...),
    vendor_id: Optional[int] = Form(None),
    invoice_file: Optional[UploadFile] = File(None),
    file: Optional[UploadFile] = File(None),
    proof_photo: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db),
):
    """
    Submit a vendor invoice for review.

    Accepts multipart/form-data with:
    - campaign_id, budget_line_id, invoice_number (required)
    - vendor_id (optional, derived from budget line if omitted)
    - invoice_file / file: the invoice or receipt (PDF/image)
    - proof_photo: optional photo verifying delivery/completion
    """
    campaign = _get_or_404(db, Campaign, campaign_id)
    budget_line = _get_or_404(db, BudgetLine, budget_line_id)

    if vendor_id is None:
        vendor_id = budget_line.vendor_id
    if vendor_id is None:
        raise HTTPException(status_code=400, detail="Budget line has no assigned vendor.")

    vendor = _get_or_404(db, Vendor, vendor_id)

    if budget_line.campaign_id != campaign_id:
        raise HTTPException(status_code=400, detail="Budget line does not belong to this campaign.")
    if vendor.campaign_id != campaign_id:
        raise HTTPException(status_code=400, detail="Vendor does not belong to this campaign.")

    # --- Validate file ---
    actual_file = invoice_file or file
    if actual_file is None:
        raise HTTPException(status_code=400, detail="Please attach an invoice file (PDF or image).")

    content_type = actual_file.content_type or "application/octet-stream"
    if content_type not in _ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported file type '{content_type}'. Allowed: PDF, JPEG, PNG, WEBP.",
        )

    # --- Save files ---
    os.makedirs(settings.upload_dir, exist_ok=True)
    ext = Path(actual_file.filename or "invoice").suffix or ".bin"
    unique_name = f"{uuid.uuid4().hex}{ext}"
    abs_save_path = os.path.join(settings.upload_dir, unique_name)

    with open(abs_save_path, "wb") as f_out:
        shutil.copyfileobj(actual_file.file, f_out)
    web_file_path = f"uploads/{unique_name}"

    abs_proof_path = None
    web_proof_path = None
    if proof_photo and proof_photo.filename:
        proof_ext = Path(proof_photo.filename).suffix or ".jpg"
        proof_unique_name = f"proof_{uuid.uuid4().hex}{proof_ext}"
        abs_proof_path = os.path.join(settings.upload_dir, proof_unique_name)
        with open(abs_proof_path, "wb") as f_out:
            shutil.copyfileobj(proof_photo.file, f_out)
        web_proof_path = f"uploads/{proof_unique_name}"

    # --- Create initial Invoice row (SUBMITTED) ---
    invoice = Invoice(
        campaign_id=campaign_id,
        budget_line_id=budget_line_id,
        vendor_id=vendor_id,
        invoice_number=invoice_number,
        amount=0.0,
        currency=campaign.currency,
        payout_email=vendor.payout_email,
        raw_file_path=web_file_path,
        evidence_path=web_proof_path or web_file_path,
        status="SUBMITTED",
    )
    db.add(invoice)
    db.commit()
    db.refresh(invoice)
    audit.log(db, actor="system", action="invoice.submitted", campaign_id=campaign_id, invoice_id=invoice.id)

    # --- LLM Extraction ---
    try:
        extracted: ExtractionResult = await asyncio.wait_for(
            extraction_module.extract_invoice(abs_save_path, content_type), timeout=130
        )
    except Exception as exc:
        invoice.status = "NEEDS_REVIEW"
        reason = str(exc) or "Invoice extraction timed out. Please try again shortly."
        invoice.ai_summary = f"Extraction failed: {reason}"
        db.commit()
        audit.log(
            db,
            actor="system",
            action="invoice.extraction_failed",
            invoice_id=invoice.id,
            detail=str(exc),
        )
        raise HTTPException(status_code=422, detail=f"Invoice extraction failed: {reason}")

    invoice.extracted_json = extracted.model_dump_json()
    invoice.amount = extracted.amount
    invoice.currency = extracted.currency or campaign.currency
    invoice.payout_email = extracted.payout_email or vendor.payout_email
    invoice.description = extracted.description
    invoice.status = "EXTRACTED"
    db.commit()
    audit.log(db, actor="system", action="invoice.extracted", invoice_id=invoice.id)

    # --- Policy checks ---
    invoice_data = {
        "payout_email": invoice.payout_email,
        "invoice_number": invoice.invoice_number,
        "amount": invoice.amount,
        "currency": invoice.currency,
        "evidence_path": invoice.evidence_path,
        "proof_file_attached": bool(abs_proof_path and os.path.exists(abs_proof_path)),
    }
    existing_invoices = (
        db.query(Invoice)
        .filter(Invoice.campaign_id == campaign_id, Invoice.id != invoice.id)
        .all()
    )
    invoice_data["committed_amount"] = sum(
        max(0.0, other.amount - other.paid_amount)
        for other in existing_invoices
        if other.budget_line_id == budget_line_id and other.status in {
            "AWAITING_FUNDS", "PARTIALLY_PAID", "PAYOUT_PENDING", "FAILED"
        } and any(v.decision == "approve" for v in other.verifications)
    )
    policy_results = run_policy_checks(invoice_data, campaign, budget_line, vendor, existing_invoices)

    for result in policy_results:
        check_row = Check(
            invoice_id=invoice.id,
            check_name=result.check_name,
            passed=result.passed,
            severity=result.severity,
            source=result.source,
            detail=result.detail,
        )
        db.add(check_row)

    invoice.status = "CHECKED"
    db.commit()
    audit.log(db, actor="system", action="invoice.checked", invoice_id=invoice.id)

    any_hard_fail = any(not r.passed and r.severity == "hard" for r in policy_results)

    # --- Advisory checks (soft, non-blocking) ---
    try:
        advisory_result: AdvisoryResult = await asyncio.wait_for(advisory_module.run_advisory_checks(
            extracted=extracted,
            budget_line_name=budget_line.name,
            evidence_path=abs_proof_path or abs_save_path,
        ), timeout=25)
        summary_parts = [advisory_result.summary]
        if advisory_result.flags:
            summary_parts.append("Advisory flags: " + "; ".join(advisory_result.flags))
        invoice.ai_summary = "\n".join(summary_parts)
    except TimeoutError:
        invoice.ai_summary = "AI advisory timed out. Review the invoice and proof manually; payout checks are unaffected."
    except Exception as exc:
        invoice.ai_summary = f"Advisory checks could not be completed: {exc}"

    # --- Determine final status ---
    if any_hard_fail:
        invoice.status = "REJECTED"
        audit.log(
            db,
            actor="system",
            action="invoice.rejected",
            invoice_id=invoice.id,
            detail={"hard_failures": [r.check_name for r in policy_results if not r.passed]},
        )
    else:
        invoice.status = "AWAITING_VERIFIER"
        audit.log(db, actor="system", action="invoice.awaiting_verifier", invoice_id=invoice.id)

    db.commit()
    db.refresh(invoice)
    return _invoice_to_detail(invoice)


# ---------------------------------------------------------------------------
# Endpoint 7 â€” Get invoice detail
# ---------------------------------------------------------------------------


@router.get("/invoices", response_model=list[InvoiceDetail])
def list_all_invoices(
    campaign_id: Optional[int] = None,
    status: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """List invoices, optionally filtered by campaign_id and status."""
    query = db.query(Invoice)
    if campaign_id is not None:
        query = query.filter(Invoice.campaign_id == campaign_id)
    if status:
        query = query.filter(Invoice.status == status)
    invoices = query.order_by(Invoice.created_at.desc()).all()
    return [_invoice_to_detail(inv) for inv in invoices]


@router.get("/invoices/{invoice_id}", response_model=InvoiceDetail)
def get_invoice(invoice_id: int, db: Session = Depends(get_db)):
    """Retrieve full invoice detail including checks, verifications, and payout."""
    invoice = _get_or_404(db, Invoice, invoice_id)
    return _invoice_to_detail(invoice)


# ---------------------------------------------------------------------------
# Endpoint 8 â€” List invoices for a campaign
# ---------------------------------------------------------------------------


@router.get("/campaigns/{campaign_id}/invoices", response_model=list[InvoiceOut])
def list_invoices(campaign_id: int, db: Session = Depends(get_db)):
    """Return all invoices for a given campaign."""
    _get_or_404(db, Campaign, campaign_id)
    invoices = (
        db.query(Invoice)
        .filter_by(campaign_id=campaign_id)
        .order_by(Invoice.created_at.desc())
        .all()
    )
    return [InvoiceOut.model_validate(inv) for inv in invoices]


# ---------------------------------------------------------------------------
# Endpoint 9 â€” Approve invoice (human verifier)
# ---------------------------------------------------------------------------


def _record_payout_result(invoice, payout, campaign, budget_line, response):
    """Credit accounting only after the recipient transaction succeeds."""
    if response.get("simulated") or (response.get("batch_header", {}).get("payout_batch_id") or payout.paypal_batch_id or "").startswith("SANDBOX-"):
        raise PayPalError(409, {"error": "Payout was simulated; no money was sent. Configure an enabled sandbox payout account."})
    header = response.get("batch_header", {})
    payout.paypal_batch_id = header.get("payout_batch_id") or payout.paypal_batch_id
    payout.sender_batch_id = header.get("sender_batch_header", {}).get("sender_batch_id") or payout.sender_batch_id
    items = response.get("items", [])
    succeeded = bool(items) and all(item.get("transaction_status") == "SUCCESS" for item in items)
    failed = header.get("batch_status") in {"DENIED", "CANCELED"} or any(
        item.get("transaction_status") in {"FAILED", "BLOCKED", "RETURNED", "REFUNDED"} for item in items
    )
    if succeeded and payout.status != "success":
        campaign.pool_balance -= invoice.amount
        budget_line.paid_amount += invoice.amount
    payout.status = "success" if succeeded else "failed" if failed else "pending"
    invoice.status = "PAID" if succeeded else "FAILED" if failed else "PAYOUT_PENDING"


_PAYOUT_WAIT_SECONDS = 40


async def _pay_with_deadline(db: Session, invoice: Invoice) -> None:
    """Return the verifier request even if PayPal does not answer promptly."""
    try:
        await asyncio.wait_for(pay_available(db, invoice, paypal), timeout=_PAYOUT_WAIT_SECONDS)
    except TimeoutError:
        db.rollback()
        audit.log(db, actor="system", action="payout.response_timeout",
                  campaign_id=invoice.campaign_id, invoice_id=invoice.id,
                  detail="PayPal response timed out; check the existing installment before retrying.")
        db.expire_all()


@router.post("/invoices/{invoice_id}/approve", response_model=InvoiceDetail)
async def approve_invoice(
    invoice_id: int,
    payload: VerificationCreate,
    db: Session = Depends(get_db),
):
    """
    Approve an invoice as a human verifier and trigger the vendor payout.

    Only invoices in AWAITING_VERIFIER status can be approved.
    Triggers a PayPal payout; status progresses to PAYOUT_PENDING then PAID
    (or FAILED if PayPal returns an error).
    """
    invoice = _get_or_404(db, Invoice, invoice_id)
    if payload.override_for_testing:
        if not settings.enable_verifier_test_override or settings.paypal_base_url.rstrip("/") != "https://api-m.sandbox.paypal.com":
            raise HTTPException(status_code=403, detail="Verifier test override is available only in PayPal Sandbox when enabled.")
        if invoice.status not in {"REJECTED", "AWAITING_VERIFIER", "NEEDS_REVIEW"}:
            raise HTTPException(status_code=409, detail="Only an unpaid, unapproved invoice can use the test override.")
        campaign = _get_or_404(db, Campaign, invoice.campaign_id)
        budget_line = _get_or_404(db, BudgetLine, invoice.budget_line_id)
        vendor = _get_or_404(db, Vendor, invoice.vendor_id)
        if budget_line.campaign_id != campaign.id or vendor.campaign_id != campaign.id:
            raise HTTPException(status_code=409, detail="Invoice vendor and budget line must belong to this campaign.")
        if not math.isfinite(invoice.amount) or invoice.amount <= 0:
            raise HTTPException(status_code=409, detail="A positive invoice amount is required to test a payout.")
        original_email = invoice.payout_email
        invoice.payout_email = vendor.payout_email
        invoice.currency = campaign.currency
        audit.log(db, actor=f"verifier:{payload.verifier_name}", action="invoice.sandbox_test_override",
                  campaign_id=invoice.campaign_id, invoice_id=invoice.id,
                  detail={"reason": payload.note or "Sandbox payout test",
                          "bypassed_checks": [c.check_name for c in invoice.checks if not c.passed],
                          "invoice_payout_email": original_email,
                          "registered_vendor_email": vendor.payout_email})
    else:
        _guard_invoice_status(invoice, "AWAITING_VERIFIER")

    # Record verification decision
    verification = Verification(
        invoice_id=invoice_id,
        verifier_name=payload.verifier_name,
        decision="test_override" if payload.override_for_testing else "approve",
        note=payload.note or ("Sandbox payout test" if payload.override_for_testing else None),
    )
    db.add(verification)
    audit.log(
        db,
        actor=f"verifier:{payload.verifier_name}",
        action="invoice.approved",
        invoice_id=invoice_id,
    )

    # Retrieve dependencies for payout
    vendor = db.get(Vendor, invoice.vendor_id)
    campaign = db.get(Campaign, invoice.campaign_id)
    budget_line = db.get(BudgetLine, invoice.budget_line_id)

    if vendor is None or campaign is None or budget_line is None:
        raise HTTPException(status_code=500, detail="Data integrity error: related records missing.")

    invoice.status = "AWAITING_FUNDS"
    db.commit()
    await _pay_with_deadline(db, invoice)

    db.refresh(invoice)
    return _invoice_to_detail(invoice)


# ---------------------------------------------------------------------------
# Endpoint 10 â€” Reject invoice (human verifier)
# ---------------------------------------------------------------------------


@router.post("/invoices/{invoice_id}/reject", response_model=InvoiceDetail)
def reject_invoice(
    invoice_id: int,
    payload: VerificationCreate,
    db: Session = Depends(get_db),
):
    """
    Reject an invoice as a human verifier.

    Only invoices in AWAITING_VERIFIER status can be rejected this way.
    """
    invoice = _get_or_404(db, Invoice, invoice_id)
    _guard_invoice_status(invoice, "AWAITING_VERIFIER")

    verification = Verification(
        invoice_id=invoice_id,
        verifier_name=payload.verifier_name,
        decision="reject",
        note=payload.note,
    )
    db.add(verification)
    invoice.status = "VERIFIER_REJECTED"
    db.commit()
    audit.log(
        db,
        actor=f"verifier:{payload.verifier_name}",
        action="invoice.verifier_rejected",
        invoice_id=invoice_id,
        detail={"note": payload.note},
    )
    db.refresh(invoice)
    return _invoice_to_detail(invoice)


# ---------------------------------------------------------------------------
# Endpoint 11 â€” Retry failed invoice
# ---------------------------------------------------------------------------


@router.post("/invoices/{invoice_id}/retry", response_model=InvoiceDetail)
async def retry_invoice(
    invoice_id: int,
    payload: VerificationCreate,
    db: Session = Depends(get_db),
):
    """
    Retry a payout for an invoice in FAILED status.

    Checks payout status first; if not already in a terminal success state,
    re-triggers the PayPal payout.
    """
    invoice = _get_or_404(db, Invoice, invoice_id)
    if invoice.status not in {"FAILED", "PAYOUT_PENDING", "PARTIALLY_PAID", "AWAITING_FUNDS"}:
        raise HTTPException(status_code=409, detail="Only failed or pending payouts can be checked or retried.")

    vendor = db.get(Vendor, invoice.vendor_id)
    campaign = db.get(Campaign, invoice.campaign_id)
    budget_line = db.get(BudgetLine, invoice.budget_line_id)

    if vendor is None or campaign is None or budget_line is None:
        raise HTTPException(status_code=500, detail="Data integrity error: related records missing.")

    # Reconcile the existing transfer before attempting another installment.
    if invoice.installments:
        invoice.status = "PARTIALLY_PAID" if invoice.paid_amount > 0 else "AWAITING_FUNDS"
        db.commit()
        await _pay_with_deadline(db, invoice)
    else:
        raise HTTPException(status_code=409, detail="This legacy payout requires manual PayPal reconciliation.")

    db.refresh(invoice)
    return _invoice_to_detail(invoice)


# ---------------------------------------------------------------------------
# Endpoint 12 â€” Public ledger
# ---------------------------------------------------------------------------


@router.get("/campaigns/{campaign_id}/ledger", response_model=list[LedgerEntry])
def get_ledger(campaign_id: int, db: Session = Depends(get_db)):
    """
    Return the public transparency ledger for a campaign.

    Combines all captured donations and completed payouts in chronological
    order so that donors can see exactly how their money was spent.
    """
    _get_or_404(db, Campaign, campaign_id)

    entries: list[LedgerEntry] = []

    # Donations
    donations = db.query(Donation).filter_by(campaign_id=campaign_id).all()
    for d in donations:
        entries.append(
            LedgerEntry(
                type="donation",
                amount=d.amount,
                actor_name=d.donor_name,
                status=d.status,
                created_at=d.created_at,
                proof_url=None,
            )
        )

    # One ledger entry per confirmed installment; include earlier single payouts.
    invoices = db.query(Invoice).filter_by(campaign_id=campaign_id).all()
    for inv in invoices:
        proof_url = f"/uploads/{Path(inv.evidence_path).name}" if inv.evidence_path else None
        vendor = db.get(Vendor, inv.vendor_id)
        if inv.payout and inv.payout.status == "success":
            entries.append(LedgerEntry(type="payout", amount=inv.payout.amount,
                actor_name=vendor.name if vendor else "Unknown Vendor", status="success",
                created_at=inv.payout.created_at, proof_url=proof_url))
        for part in inv.installments:
            if part.status == "success":
                entries.append(LedgerEntry(type="payout", amount=part.amount,
                    actor_name=vendor.name if vendor else "Unknown Vendor", status="success",
                    created_at=part.created_at, proof_url=proof_url))

    # Sort chronologically
    entries.sort(key=lambda e: e.created_at)
    return entries


# ---------------------------------------------------------------------------
# Mount routes under both root / and /api prefix
# ---------------------------------------------------------------------------
app.include_router(router)
app.include_router(router, prefix="/api")

