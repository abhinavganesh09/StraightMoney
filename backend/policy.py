"""
policy.py — Pure rule-based policy checks for invoice validation.

No LLM, no network calls, no database I/O.  All functions take plain data
structures and return CheckResult lists so they are trivially unit-testable.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from schemas import CheckResult

# ---------------------------------------------------------------------------
# Individual check helpers
# ---------------------------------------------------------------------------


def _make(check_name: str, passed: bool, detail: str) -> CheckResult:
    """Build a hard-rule CheckResult (severity always 'hard', source always 'rule')."""
    return CheckResult(
        check_name=check_name,
        passed=passed,
        severity="hard",
        source="rule",
        detail=detail,
    )


def check_campaign_active(campaign: Any) -> CheckResult:
    """Campaign must have status == 'active'."""
    passed = campaign.status == "active"
    detail = (
        "Campaign is active."
        if passed
        else f"Campaign status is '{campaign.status}', expected 'active'."
    )
    return _make("campaign_active", passed, detail)


def check_vendor_approved(vendor: Any, budget_line: Any) -> CheckResult:
    """Vendor must be active and assigned to the claimed budget line."""
    vendor_active = vendor.status == "active"
    vendor_matches = vendor.id == budget_line.vendor_id

    if not vendor_active:
        detail = f"Vendor '{vendor.name}' is not active (status='{vendor.status}')."
        return _make("vendor_approved", False, detail)
    if not vendor_matches:
        detail = (
            f"Vendor id={vendor.id} is not the assigned vendor "
            f"for budget line id={budget_line.id} "
            f"(expected vendor_id={budget_line.vendor_id})."
        )
        return _make("vendor_approved", False, detail)
    return _make("vendor_approved", True, "Vendor is active and assigned to this budget line.")


def check_payout_email_match(invoice_data: dict, vendor: Any) -> CheckResult:
    """Payout email on the invoice must match the vendor's registered email."""
    passed = invoice_data.get("payout_email", "").strip().lower() == vendor.payout_email.strip().lower()
    detail = (
        "Payout email matches vendor record."
        if passed
        else (
            f"Invoice payout email '{invoice_data.get('payout_email')}' does not match "
            f"vendor email '{vendor.payout_email}'."
        )
    )
    return _make("payout_email_match", passed, detail)


def check_no_duplicate(invoice_data: dict, vendor: Any, existing_invoices: list) -> CheckResult:
    """No submitted invoice may share this vendor and invoice number."""
    duplicates = [
        inv
        for inv in existing_invoices
        if (
            inv.vendor_id == vendor.id
            and inv.invoice_number == invoice_data.get("invoice_number")
        )
    ]
    passed = len(duplicates) == 0
    detail = (
        "No duplicate invoice found."
        if passed
        else (
            f"Duplicate invoice found: invoice_number='{invoice_data.get('invoice_number')}' "
            f"already exists for vendor id={vendor.id} with status(es) "
            f"{[d.status for d in duplicates]}."
        )
    )
    return _make("no_duplicate", passed, detail)


def check_within_budget_line(invoice_data: dict, budget_line: Any) -> CheckResult:
    """Invoice amount must not exceed the remaining budget on the line."""
    remaining = budget_line.budgeted_amount - budget_line.paid_amount - float(invoice_data.get("committed_amount", 0))
    amount = float(invoice_data.get("amount", 0))
    passed = amount <= remaining
    detail = (
        f"Amount {amount} is within remaining budget {remaining:.2f}."
        if passed
        else (
            f"Invoice amount {amount} exceeds remaining budget line balance "
            f"{remaining:.2f} (budgeted={budget_line.budgeted_amount}, "
            f"paid={budget_line.paid_amount})."
        )
    )
    return _make("within_budget_line", passed, detail)


def check_pool_has_funds(invoice_data: dict, campaign: Any) -> CheckResult:
    """Report funds available for an installment without blocking approval."""
    amount = float(invoice_data.get("amount", 0))
    available = min(amount, max(0.0, campaign.pool_balance))
    detail = (
        f"{available:.2f} available for the first payout; "
        f"{max(0.0, amount - available):.2f} will remain owed after approval."
    )
    return _make("pool_has_funds", True, detail)


def check_currency_match(invoice_data: dict, campaign: Any) -> CheckResult:
    """Invoice currency must match the campaign's base currency."""
    inv_currency = invoice_data.get("currency", "").upper()
    camp_currency = campaign.currency.upper()
    passed = inv_currency == camp_currency
    detail = (
        f"Currency '{inv_currency}' matches campaign currency."
        if passed
        else (
            f"Currency mismatch: invoice is '{inv_currency}' but campaign "
            f"uses '{camp_currency}'."
        )
    )
    return _make("currency_match", passed, detail)


def check_evidence_attached(invoice_data: dict) -> CheckResult:
    """A proof file must have been uploaded and identified by the caller."""
    passed = invoice_data.get("proof_file_attached") is True
    detail = (
        "Proof photo is attached."
        if passed
        else "No proof photo was uploaded with this invoice."
    )
    return _make("evidence_attached", passed, detail)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def run_policy_checks(
    invoice_data: dict,
    campaign: Any,
    budget_line: Any,
    vendor: Any,
    existing_invoices: list,
) -> list[CheckResult]:
    """
    Run all 8 hard policy checks in order and return the full results list.

    Args:
        invoice_data:      Dict with keys: payout_email, invoice_number, amount,
                           currency, proof_file_attached.
        campaign:          ORM Campaign (or any object with .status, .pool_balance,
                           .currency attributes).
        budget_line:       ORM BudgetLine (or equivalent).
        vendor:            ORM Vendor (or equivalent).
        existing_invoices: List of ORM Invoice objects for duplicate detection.

    Returns:
        Ordered list of 8 CheckResult objects.
    """
    return [
        check_campaign_active(campaign),
        check_vendor_approved(vendor, budget_line),
        check_payout_email_match(invoice_data, vendor),
        check_no_duplicate(invoice_data, vendor, existing_invoices),
        check_within_budget_line(invoice_data, budget_line),
        check_pool_has_funds(invoice_data, campaign),
        check_currency_match(invoice_data, campaign),
        check_evidence_attached(invoice_data),
    ]


@dataclass(frozen=True)
class PolicyDecision:
    checks: list[CheckResult]
    routing: str
    reasons: list[str]


def evaluate_policy(
    invoice_data: dict,
    campaign: Any,
    budget_line: Any,
    vendor: Any,
    existing_invoices: list,
) -> PolicyDecision:
    """Run all hard checks in spec order and explain the routing decision."""
    checks = run_policy_checks(
        invoice_data, campaign, budget_line, vendor, existing_invoices
    )
    reasons = [check.detail for check in checks if not check.passed]
    routing = "REJECTED" if reasons else "AWAITING_VERIFIER"
    return PolicyDecision(checks=checks, routing=routing, reasons=reasons)
