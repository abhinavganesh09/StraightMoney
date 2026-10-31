"""
tests/test_policy.py — Comprehensive pytest tests for all 8 policy checks.

Uses plain Python mock objects (simple namespaces) — no database required.
Run with:  pytest tests/test_policy.py -v
"""

from __future__ import annotations

import sys
import os

# Ensure the backend package root is importable when running from project root
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from policy import (
    check_campaign_active,
    check_currency_match,
    check_evidence_attached,
    check_no_duplicate,
    check_pool_has_funds,
    check_payout_email_match,
    check_vendor_approved,
    check_within_budget_line,
    evaluate_policy,
    run_policy_checks,
)
from schemas import CheckResult

# ---------------------------------------------------------------------------
# Mock helpers
# ---------------------------------------------------------------------------


class _Obj:
    """Tiny namespace for creating mock ORM objects."""

    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


def make_campaign(status="active", pool_balance=500.0, currency="USD"):
    return _Obj(status=status, pool_balance=pool_balance, currency=currency)


def make_vendor(id=1, status="active", payout_email="vendor@example.com", campaign_id=1):
    return _Obj(id=id, status=status, payout_email=payout_email, campaign_id=campaign_id, name="Test Vendor")


def make_budget_line(id=10, campaign_id=1, vendor_id=1, budgeted_amount=400.0, paid_amount=0.0):
    return _Obj(
        id=id,
        campaign_id=campaign_id,
        vendor_id=vendor_id,
        budgeted_amount=budgeted_amount,
        paid_amount=paid_amount,
    )


def make_invoice_data(
    payout_email="vendor@example.com",
    invoice_number="INV-001",
    amount=100.0,
    currency="USD",
    proof_file_attached=True,
):
    return {
        "payout_email": payout_email,
        "invoice_number": invoice_number,
        "amount": amount,
        "currency": currency,
        "proof_file_attached": proof_file_attached,
    }


def make_existing_invoice(vendor_id=1, invoice_number="INV-OLD", status="AWAITING_VERIFIER"):
    return _Obj(vendor_id=vendor_id, invoice_number=invoice_number, status=status)


# ---------------------------------------------------------------------------
# 1. campaign_active
# ---------------------------------------------------------------------------


class TestCampaignActive:
    def test_passes_when_active(self):
        result = check_campaign_active(make_campaign(status="active"))
        assert result.passed is True
        assert result.check_name == "campaign_active"
        assert result.severity == "hard"
        assert result.source == "rule"

    def test_fails_when_draft(self):
        result = check_campaign_active(make_campaign(status="draft"))
        assert result.passed is False
        assert "draft" in result.detail

    def test_fails_when_closed(self):
        result = check_campaign_active(make_campaign(status="closed"))
        assert result.passed is False
        assert "closed" in result.detail


# ---------------------------------------------------------------------------
# 2. vendor_approved
# ---------------------------------------------------------------------------


class TestVendorApproved:
    def test_passes_when_active_and_assigned(self):
        vendor = make_vendor(id=5, status="active")
        budget_line = make_budget_line(vendor_id=5)
        result = check_vendor_approved(vendor, budget_line)
        assert result.passed is True

    def test_fails_when_vendor_inactive(self):
        vendor = make_vendor(id=5, status="inactive")
        budget_line = make_budget_line(vendor_id=5)
        result = check_vendor_approved(vendor, budget_line)
        assert result.passed is False
        assert "inactive" in result.detail

    def test_fails_when_wrong_vendor_for_budget_line(self):
        vendor = make_vendor(id=5, status="active")
        budget_line = make_budget_line(vendor_id=9)  # different vendor
        result = check_vendor_approved(vendor, budget_line)
        assert result.passed is False
        assert "not the assigned vendor" in result.detail


# ---------------------------------------------------------------------------
# 3. payout_email_match
# ---------------------------------------------------------------------------


class TestPayoutEmailMatch:
    def test_passes_when_emails_match(self):
        data = make_invoice_data(payout_email="vendor@example.com")
        vendor = make_vendor(payout_email="vendor@example.com")
        result = check_payout_email_match(data, vendor)
        assert result.passed is True

    def test_passes_case_insensitive(self):
        data = make_invoice_data(payout_email="Vendor@Example.COM")
        vendor = make_vendor(payout_email="vendor@example.com")
        result = check_payout_email_match(data, vendor)
        assert result.passed is True

    def test_fails_when_emails_differ(self):
        data = make_invoice_data(payout_email="attacker@evil.com")
        vendor = make_vendor(payout_email="vendor@example.com")
        result = check_payout_email_match(data, vendor)
        assert result.passed is False
        assert "attacker@evil.com" in result.detail


# ---------------------------------------------------------------------------
# 4. no_duplicate
# ---------------------------------------------------------------------------


class TestNoDuplicate:
    def test_passes_when_no_existing_invoices(self):
        data = make_invoice_data(invoice_number="INV-001")
        vendor = make_vendor(id=1)
        result = check_no_duplicate(data, vendor, [])
        assert result.passed is True

    def test_fails_when_duplicate_is_rejected(self):
        data = make_invoice_data(invoice_number="INV-001")
        vendor = make_vendor(id=1)
        existing = make_existing_invoice(vendor_id=1, invoice_number="INV-001", status="REJECTED")
        result = check_no_duplicate(data, vendor, [existing])
        assert result.passed is False

    def test_fails_when_duplicate_is_verifier_rejected(self):
        data = make_invoice_data(invoice_number="INV-001")
        vendor = make_vendor(id=1)
        existing = make_existing_invoice(vendor_id=1, invoice_number="INV-001", status="VERIFIER_REJECTED")
        result = check_no_duplicate(data, vendor, [existing])
        assert result.passed is False

    def test_fails_when_active_duplicate_exists(self):
        data = make_invoice_data(invoice_number="INV-001")
        vendor = make_vendor(id=1)
        existing = make_existing_invoice(vendor_id=1, invoice_number="INV-001", status="AWAITING_VERIFIER")
        result = check_no_duplicate(data, vendor, [existing])
        assert result.passed is False
        assert "INV-001" in result.detail

    def test_passes_when_different_vendor_same_number(self):
        data = make_invoice_data(invoice_number="INV-001")
        vendor = make_vendor(id=1)
        existing = make_existing_invoice(vendor_id=2, invoice_number="INV-001", status="AWAITING_VERIFIER")
        result = check_no_duplicate(data, vendor, [existing])
        assert result.passed is True


# ---------------------------------------------------------------------------
# 5. within_budget_line
# ---------------------------------------------------------------------------


class TestWithinBudgetLine:
    def test_passes_when_amount_within_remaining(self):
        data = make_invoice_data(amount=100.0)
        budget_line = make_budget_line(budgeted_amount=400.0, paid_amount=0.0)
        result = check_within_budget_line(data, budget_line)
        assert result.passed is True

    def test_passes_when_amount_equals_remaining(self):
        data = make_invoice_data(amount=400.0)
        budget_line = make_budget_line(budgeted_amount=400.0, paid_amount=0.0)
        result = check_within_budget_line(data, budget_line)
        assert result.passed is True

    def test_fails_when_amount_exceeds_remaining(self):
        data = make_invoice_data(amount=401.0)
        budget_line = make_budget_line(budgeted_amount=400.0, paid_amount=0.0)
        result = check_within_budget_line(data, budget_line)
        assert result.passed is False
        assert "401" in result.detail or "400" in result.detail

    def test_fails_when_partly_paid_and_amount_exceeds_remaining(self):
        data = make_invoice_data(amount=200.0)
        budget_line = make_budget_line(budgeted_amount=400.0, paid_amount=250.0)
        # remaining = 150.0
        result = check_within_budget_line(data, budget_line)
        assert result.passed is False


# ---------------------------------------------------------------------------
# 6. pool_has_funds
# ---------------------------------------------------------------------------


class TestPoolHasFunds:
    def test_passes_when_pool_sufficient(self):
        data = make_invoice_data(amount=100.0)
        campaign = make_campaign(pool_balance=500.0)
        result = check_pool_has_funds(data, campaign)
        assert result.passed is True

    def test_passes_when_amount_equals_pool(self):
        data = make_invoice_data(amount=500.0)
        campaign = make_campaign(pool_balance=500.0)
        result = check_pool_has_funds(data, campaign)
        assert result.passed is True

    def test_allows_partial_when_pool_insufficient(self):
        data = make_invoice_data(amount=501.0)
        campaign = make_campaign(pool_balance=500.0)
        result = check_pool_has_funds(data, campaign)
        assert result.passed is True
        assert "1.00 will remain owed" in result.detail

    def test_allows_waiting_when_pool_is_zero(self):
        data = make_invoice_data(amount=1.0)
        campaign = make_campaign(pool_balance=0.0)
        result = check_pool_has_funds(data, campaign)
        assert result.passed is True
        assert "0.00 available" in result.detail


# ---------------------------------------------------------------------------
# 7. currency_match
# ---------------------------------------------------------------------------


class TestCurrencyMatch:
    def test_passes_when_currencies_match(self):
        data = make_invoice_data(currency="USD")
        campaign = make_campaign(currency="USD")
        result = check_currency_match(data, campaign)
        assert result.passed is True

    def test_passes_case_insensitive(self):
        data = make_invoice_data(currency="usd")
        campaign = make_campaign(currency="USD")
        result = check_currency_match(data, campaign)
        assert result.passed is True

    def test_fails_when_currencies_differ(self):
        data = make_invoice_data(currency="EUR")
        campaign = make_campaign(currency="USD")
        result = check_currency_match(data, campaign)
        assert result.passed is False
        assert "EUR" in result.detail


# ---------------------------------------------------------------------------
# 8. evidence_attached
# ---------------------------------------------------------------------------


class TestEvidenceAttached:
    def test_passes_when_proof_photo_attached(self):
        result = check_evidence_attached(make_invoice_data(proof_file_attached=True))
        assert result.passed is True
        assert result.check_name == "evidence_attached"
        assert result.severity == "hard"
        assert result.detail

    def test_fails_when_proof_photo_missing(self):
        result = check_evidence_attached(make_invoice_data(proof_file_attached=False))
        assert result.passed is False
        assert "proof photo" in result.detail.lower()

    def test_invoice_file_alone_is_not_proof(self):
        data = make_invoice_data(proof_file_attached=False)
        data["invoice_file_id"] = 7
        assert check_evidence_attached(data).passed is False


# ---------------------------------------------------------------------------
# 9. run_policy_checks integration
# ---------------------------------------------------------------------------


class TestRunPolicyChecks:
    def _all_passing_setup(self):
        campaign = make_campaign(status="active", pool_balance=1000.0, currency="USD")
        vendor = make_vendor(id=1, status="active", payout_email="vendor@example.com")
        budget_line = make_budget_line(vendor_id=1, budgeted_amount=500.0, paid_amount=0.0)
        invoice_data = make_invoice_data(
            payout_email="vendor@example.com",
            invoice_number="INV-100",
            amount=200.0,
            currency="USD",
            proof_file_attached=True,
        )
        return invoice_data, campaign, budget_line, vendor

    def test_returns_8_results(self):
        invoice_data, campaign, budget_line, vendor = self._all_passing_setup()
        results = run_policy_checks(invoice_data, campaign, budget_line, vendor, [])
        assert len(results) == 8

    def test_all_checks_pass_in_happy_path(self):
        invoice_data, campaign, budget_line, vendor = self._all_passing_setup()
        results = run_policy_checks(invoice_data, campaign, budget_line, vendor, [])
        failed = [r for r in results if not r.passed]
        assert failed == [], f"Unexpected failures: {[r.check_name for r in failed]}"

    def test_all_results_are_check_result_instances(self):
        invoice_data, campaign, budget_line, vendor = self._all_passing_setup()
        results = run_policy_checks(invoice_data, campaign, budget_line, vendor, [])
        for r in results:
            assert isinstance(r, CheckResult)

    def test_all_results_have_hard_severity(self):
        invoice_data, campaign, budget_line, vendor = self._all_passing_setup()
        results = run_policy_checks(invoice_data, campaign, budget_line, vendor, [])
        for r in results:
            assert r.severity == "hard"

    def test_all_results_have_rule_source(self):
        invoice_data, campaign, budget_line, vendor = self._all_passing_setup()
        results = run_policy_checks(invoice_data, campaign, budget_line, vendor, [])
        for r in results:
            assert r.source == "rule"

    def test_check_order_matches_spec(self):
        invoice_data, campaign, budget_line, vendor = self._all_passing_setup()
        results = run_policy_checks(invoice_data, campaign, budget_line, vendor, [])
        expected_names = [
            "campaign_active",
            "vendor_approved",
            "payout_email_match",
            "no_duplicate",
            "within_budget_line",
            "pool_has_funds",
            "currency_match",
            "evidence_attached",
        ]
        assert [r.check_name for r in results] == expected_names

    def test_single_hard_fail_detected(self):
        invoice_data, campaign, budget_line, vendor = self._all_passing_setup()
        campaign.status = "draft"  # break one check
        results = run_policy_checks(invoice_data, campaign, budget_line, vendor, [])
        failures = [r for r in results if not r.passed]
        assert len(failures) == 1
        assert failures[0].check_name == "campaign_active"

    def test_multiple_failures_detected(self):
        invoice_data, campaign, budget_line, vendor = self._all_passing_setup()
        campaign.status = "draft"
        invoice_data["currency"] = "EUR"
        results = run_policy_checks(invoice_data, campaign, budget_line, vendor, [])
        failures = [r for r in results if not r.passed]
        failure_names = {r.check_name for r in failures}
        assert "campaign_active" in failure_names
        assert "currency_match" in failure_names

    def test_no_duplicate_check_uses_existing_invoices(self):
        invoice_data, campaign, budget_line, vendor = self._all_passing_setup()
        existing = make_existing_invoice(vendor_id=1, invoice_number="INV-100", status="CHECKED")
        results = run_policy_checks(invoice_data, campaign, budget_line, vendor, [existing])
        dup_result = next(r for r in results if r.check_name == "no_duplicate")
        assert dup_result.passed is False


class TestPolicyRouting:
    def test_passing_checks_await_verifier(self):
        invoice_data, campaign, budget_line, vendor = TestRunPolicyChecks()._all_passing_setup()
        decision = evaluate_policy(invoice_data, campaign, budget_line, vendor, [])
        assert decision.routing == "AWAITING_VERIFIER"
        assert decision.reasons == []
        assert len(decision.checks) == 8

    def test_failed_checks_reject_with_reasons(self):
        invoice_data, campaign, budget_line, vendor = TestRunPolicyChecks()._all_passing_setup()
        campaign.status = "draft"
        invoice_data["currency"] = "EUR"
        decision = evaluate_policy(invoice_data, campaign, budget_line, vendor, [])
        assert decision.routing == "REJECTED"
        assert len(decision.reasons) == 2
        assert "draft" in decision.reasons[0]
        assert "EUR" in decision.reasons[1]
