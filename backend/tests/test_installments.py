from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from db import Base
from models import Campaign, Vendor, BudgetLine, Invoice, Verification, PayoutInstallment
from installments import pay_available, pay_campaign
import pytest


class FakePayPal:
    def __init__(self):
        self.sent = []

    async def create_payout(self, **kwargs):
        self.sent.append(kwargs)
        return {"batch_header": {"payout_batch_id": f"BATCH-{len(self.sent)}"},
                "items": [{"transaction_status": "SUCCESS"}]}

    async def get_payout_status(self, batch_id):
        return {"batch_header": {"payout_batch_id": batch_id},
                "items": [{"transaction_status": "SUCCESS"}]}


def setup_invoice():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    db = Session(engine)
    campaign = Campaign(title="Test", goal_amount=1000, currency="USD", pool_balance=200,
                        status="active", organizer_name="Organizer")
    db.add(campaign)
    db.flush()
    vendor = Vendor(campaign_id=campaign.id, name="Vendor", payout_email="vendor@example.com", status="active")
    db.add(vendor)
    db.flush()
    line = BudgetLine(campaign_id=campaign.id, name="Work", vendor_id=vendor.id, budgeted_amount=1000, paid_amount=0)
    db.add(line)
    db.flush()
    invoice = Invoice(campaign_id=campaign.id, budget_line_id=line.id, vendor_id=vendor.id,
                      invoice_number="INV-1", amount=1000, currency="USD", payout_email=vendor.payout_email,
                      status="AWAITING_FUNDS")
    db.add(invoice)
    db.flush()
    db.add(Verification(invoice_id=invoice.id, verifier_name="Reviewer", decision="approve"))
    db.commit()
    return db, campaign, line, invoice


@pytest.mark.asyncio
async def test_partial_then_later_donation_finishes_invoice():
    db, campaign, line, invoice = setup_invoice()
    paypal = FakePayPal()
    await pay_available(db, invoice, paypal)
    assert invoice.status == "PARTIALLY_PAID"
    assert invoice.paid_amount == 200
    assert invoice.remaining_amount == 800
    assert campaign.pool_balance == 0
    campaign.pool_balance += 800
    db.commit()
    await pay_campaign(db, campaign.id, paypal)
    assert invoice.status == "PAID"
    assert invoice.paid_amount == 1000
    assert line.paid_amount == 1000
    assert campaign.pool_balance == 0
    assert [item["amount"] for item in paypal.sent] == [200, 800]
    assert paypal.sent[0]["installment_id"] != paypal.sent[1]["installment_id"]
    db.close()


@pytest.mark.asyncio
async def test_zero_balance_waits_without_sending():
    db, campaign, line, invoice = setup_invoice()
    campaign.pool_balance = 0
    db.commit()
    paypal = FakePayPal()
    await pay_available(db, invoice, paypal)
    assert invoice.status == "AWAITING_FUNDS"
    assert paypal.sent == []
    db.close()


@pytest.mark.asyncio
async def test_pending_transfer_is_reconciled_without_duplicate_send():
    db, campaign, line, invoice = setup_invoice()
    class PendingPayPal(FakePayPal):
        async def create_payout(self, **kwargs):
            self.sent.append(kwargs)
            return {"batch_header": {"payout_batch_id": "BATCH-PENDING"},
                    "items": [{"transaction_status": "UNCLAIMED"}]}

        async def get_payout_status(self, batch_id):
            return {"batch_header": {"payout_batch_id": batch_id},
                    "items": [{"transaction_status": "SUCCESS"}]}
    paypal = PendingPayPal()
    await pay_available(db, invoice, paypal)
    assert invoice.status == "PARTIALLY_PAID"
    assert campaign.pool_balance == 0
    await pay_available(db, invoice, paypal)
    assert len(paypal.sent) == 1
    assert len(invoice.installments) == 1
    db.close()


def test_installment_detail_exposes_remaining_amount():
    from schemas import InvoiceDetail
    db, campaign, line, invoice = setup_invoice()
    detail = InvoiceDetail.model_validate(invoice)
    assert detail.paid_amount == 0
    assert detail.remaining_amount == 1000
    assert detail.installments == []
    db.close()


@pytest.mark.asyncio
async def test_sandbox_override_pays_rejected_invoice_with_missing_proof(monkeypatch):
    import main
    from schemas import VerificationCreate
    db, campaign, line, invoice = setup_invoice()
    db.query(Verification).delete()
    invoice.status = "REJECTED"
    invoice.extracted_json = '{}'
    db.commit()
    paypal = FakePayPal()
    monkeypatch.setattr(main, "paypal", paypal)
    monkeypatch.setattr(main.settings, "enable_verifier_test_override", True)
    monkeypatch.setattr(main.settings, "paypal_base_url", "https://api-m.sandbox.paypal.com")
    result = await main.approve_invoice(invoice.id, VerificationCreate(
        verifier_name="Reviewer", note="Test the sandbox payout", override_for_testing=True), db)
    assert result.status == "PARTIALLY_PAID"
    assert result.paid_amount == 200
    assert len(paypal.sent) == 1
    db.close()


@pytest.mark.asyncio
async def test_override_routes_mismatched_invoice_to_registered_vendor(monkeypatch):
    import main
    from schemas import VerificationCreate
    db, campaign, line, invoice = setup_invoice()
    db.query(Verification).delete()
    invoice.status = "REJECTED"
    invoice.extracted_json = '{}'
    invoice.payout_email = "attacker@example.com"
    invoice.currency = "EUR"
    invoice.amount = 1500  # exceeds the approved budget line
    campaign.status = "closed"
    invoice.vendor.status = "blocked"
    db.commit()
    paypal = FakePayPal()
    monkeypatch.setattr(main, "paypal", paypal)
    monkeypatch.setattr(main.settings, "enable_verifier_test_override", True)
    monkeypatch.setattr(main.settings, "paypal_base_url", "https://api-m.sandbox.paypal.com")
    result = await main.approve_invoice(invoice.id, VerificationCreate(
        verifier_name="Sandbox tester", override_for_testing=True), db)
    assert result.status == "PARTIALLY_PAID"
    assert result.paid_amount == 200
    assert paypal.sent[0]["payout_email"] == "vendor@example.com"
    assert paypal.sent[0]["currency"] == "USD"
    assert paypal.sent[0]["amount"] == 200
    assert invoice.verifications[0].decision == "test_override"
    campaign.pool_balance += 100
    db.commit()
    await pay_campaign(db, campaign.id, paypal)
    assert len(paypal.sent) == 1
    db.close()


@pytest.mark.asyncio
async def test_override_can_be_switched_off(monkeypatch):
    import main
    from fastapi import HTTPException
    from schemas import VerificationCreate
    db, campaign, line, invoice = setup_invoice()
    invoice.status = "REJECTED"
    db.commit()
    monkeypatch.setattr(main.settings, "enable_verifier_test_override", False)
    with pytest.raises(HTTPException) as error:
        await main.approve_invoice(invoice.id, VerificationCreate(
            verifier_name="Reviewer", note="Sandbox test", override_for_testing=True), db)
    assert error.value.status_code == 403
    db.close()


@pytest.mark.asyncio
async def test_verifier_request_returns_when_paypal_stalls(monkeypatch):
    import asyncio
    import main
    from unittest.mock import AsyncMock
    from schemas import VerificationCreate
    from models import AuditLog
    db, campaign, line, invoice = setup_invoice()
    db.query(Verification).delete()
    invoice.status = "AWAITING_VERIFIER"
    db.commit()

    async def stalled_payment(*args):
        await asyncio.sleep(1)

    monkeypatch.setattr(main, "pay_available", stalled_payment)
    monkeypatch.setattr(main, "_PAYOUT_WAIT_SECONDS", 0.01)
    result = await main.approve_invoice(invoice.id, VerificationCreate(verifier_name="Reviewer"), db)
    assert result.status == "AWAITING_FUNDS"
    assert db.query(AuditLog).filter_by(invoice_id=invoice.id, action="payout.response_timeout").count() == 1
    assert invoice.installments == []
    db.close()


@pytest.mark.asyncio
async def test_async_payout_surfaces_paypal_restriction(monkeypatch):
    import httpx
    from payments import PayPalClient, PayPalError
    from unittest.mock import AsyncMock
    client = PayPalClient()
    monkeypatch.setattr(client, "_auth_headers", AsyncMock(return_value={"Authorization": "Bearer TEST"}))

    async def restricted_post(self, url, **kwargs):
        return httpx.Response(403, json={"name": "PAYOUT_NOT_AVAILABLE"}, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx.AsyncClient, "post", restricted_post)
    with pytest.raises(PayPalError) as error:
        await client.create_payout(invoice_id=123, installment_id=456, amount=10,
            currency="USD", payout_email="vendor@example.com", vendor_name="Vendor")
    assert error.value.status_code == 403


@pytest.mark.asyncio
async def test_restricted_sender_fails_without_deducting_pool():
    from payments import PayPalError
    db, campaign, line, invoice = setup_invoice()

    class RestrictedPayPal(FakePayPal):
        async def create_payout(self, **kwargs):
            raise PayPalError(403, {"name": "PAYOUT_NOT_AVAILABLE",
                                   "message": "You live in a country that is not allowed to send this payout."})

    await pay_available(db, invoice, RestrictedPayPal())
    assert invoice.status == "FAILED"
    assert invoice.paid_amount == 0
    assert campaign.pool_balance == 200
    assert line.paid_amount == 0
    assert "sandbox sender account's country" in invoice.ai_summary
    assert "debug_id" not in invoice.ai_summary
    db.close()
