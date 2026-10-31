"""
schemas.py — Pydantic v2 request/response models for StraightMoney API.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict


# ---------------------------------------------------------------------------
# Vendors
# ---------------------------------------------------------------------------


class VendorCreate(BaseModel):
    """Fields required to create a vendor inside a campaign."""

    name: str
    payout_email: str


class VendorOut(BaseModel):
    """Vendor as returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    campaign_id: int
    name: str
    payout_email: str
    status: str
    created_at: datetime


# ---------------------------------------------------------------------------
# Budget Lines
# ---------------------------------------------------------------------------


class BudgetLineCreate(BaseModel):
    """Fields required to create a budget line inside a campaign."""

    name: str
    vendor_id: Optional[int] = None
    budgeted_amount: float
    vendor_name: Optional[str] = None
    vendor_payout_email: Optional[str] = None


class BudgetLineOut(BaseModel):
    """Budget line as returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    campaign_id: int
    name: str
    vendor_id: Optional[int] = None
    vendor_name: Optional[str] = None
    budgeted_amount: float
    paid_amount: float
    created_at: datetime


# ---------------------------------------------------------------------------
# Campaigns
# ---------------------------------------------------------------------------


class CampaignCreate(BaseModel):
    """Full campaign creation payload including nested vendors and budget lines."""

    title: str
    description: Optional[str] = None
    goal_amount: float
    currency: str = "USD"
    organizer_name: str
    vendors: list[VendorCreate] = []
    budget_lines: list[BudgetLineCreate] = []


class CampaignOut(BaseModel):
    """Summarised campaign response."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    description: Optional[str]
    goal_amount: float
    currency: str
    pool_balance: float
    status: str
    organizer_name: str
    created_at: datetime


class CampaignDetail(CampaignOut):
    """Full campaign detail including nested collections."""

    model_config = ConfigDict(from_attributes=True)

    vendors: list[VendorOut] = []
    budget_lines: list[BudgetLineOut] = []


# ---------------------------------------------------------------------------
# Donations
# ---------------------------------------------------------------------------


class DonationCreate(BaseModel):
    """Payload to initiate a donation (creates a PayPal order)."""

    donor_name: str
    amount: float
    simulate: bool = False


class DonationOut(BaseModel):
    """Donation record as returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    campaign_id: int
    donor_name: str
    amount: float
    currency: str
    paypal_order_id: str
    status: str
    created_at: datetime


class DonationCaptureOut(DonationOut):
    """Extends DonationOut with PayPal capture details."""

    paypal_capture_details: Optional[dict[str, Any]] = None


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------


class CheckResult(BaseModel):
    """Result of a single policy or AI check."""

    check_name: str
    passed: bool
    severity: str  # "hard" | "soft"
    source: str  # "rule" | "ai"
    detail: str


class CheckOut(BaseModel):
    """Check row as returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    invoice_id: int
    check_name: str
    passed: bool
    severity: str
    source: str
    detail: str
    created_at: datetime


# ---------------------------------------------------------------------------
# Verifications
# ---------------------------------------------------------------------------


class VerificationCreate(BaseModel):
    """Human verifier decision payload."""

    verifier_name: str
    note: Optional[str] = None
    override_for_testing: bool = False


class VerificationOut(BaseModel):
    """Verification record as returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    invoice_id: int
    verifier_name: str
    decision: str
    note: Optional[str]
    timestamp: datetime


# ---------------------------------------------------------------------------
# Payouts
# ---------------------------------------------------------------------------


class PayoutOut(BaseModel):
    """Payout record as returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    invoice_id: int
    paypal_batch_id: Optional[str]
    sender_batch_id: Optional[str]
    status: str
    amount: float
    currency: str
    created_at: datetime


# ---------------------------------------------------------------------------
# Invoices
# ---------------------------------------------------------------------------


class PayoutInstallmentOut(PayoutOut):
    pass


class InvoiceOut(BaseModel):
    """Summarised invoice as returned in list responses."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    campaign_id: int
    budget_line_id: int
    vendor_id: int
    invoice_number: str
    amount: float
    currency: str
    payout_email: str
    description: Optional[str] = None
    evidence_path: Optional[str] = None
    raw_file_path: Optional[str] = None
    vendor_name: Optional[str] = None
    budget_line_name: Optional[str] = None
    status: str
    ai_summary: Optional[str] = None
    paid_amount: float = 0.0
    remaining_amount: float = 0.0
    created_at: datetime


class InvoiceDetail(InvoiceOut):
    """Full invoice detail including checks, verifications, and payout."""

    model_config = ConfigDict(from_attributes=True)

    checks: list[CheckOut] = []
    verifications: list[VerificationOut] = []
    payout: Optional[PayoutOut] = None
    installments: list[PayoutInstallmentOut] = []


# ---------------------------------------------------------------------------
# Ledger
# ---------------------------------------------------------------------------


class LedgerEntry(BaseModel):
    """A single entry in the public campaign ledger (donation or payout)."""

    type: str  # "donation" | "payout"
    amount: float
    actor_name: str
    status: str
    created_at: datetime
    proof_url: Optional[str] = None


# ---------------------------------------------------------------------------
# LLM result shapes
# ---------------------------------------------------------------------------


class LineItem(BaseModel):
    """A single line item extracted from an invoice."""

    description: str
    amount: float


class ExtractionResult(BaseModel):
    """Structured data extracted from an invoice file by the LLM."""

    vendor_name: str
    payout_email: str
    invoice_number: str
    amount: float
    currency: str
    description: str
    line_items: list[LineItem] = []


class AdvisoryResult(BaseModel):
    """Soft advisory flags generated by the LLM for an invoice."""

    flags: list[str]
    summary: str
