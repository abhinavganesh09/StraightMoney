"""Pay approved invoices in tracked installments as campaign funds arrive."""
from __future__ import annotations

from sqlalchemy import func
from sqlalchemy.orm import Session

from models import Campaign, Invoice, PayoutInstallment, Vendor
import audit
from payments import PayPalClient, PayPalError


def paid_amount(invoice: Invoice) -> float:
    legacy = invoice.payout.amount if invoice.payout and invoice.payout.status == "success" else 0.0
    return round(legacy + sum(part.amount for part in invoice.installments if part.status == "success"), 2)


def _status(invoice: Invoice) -> str:
    paid = paid_amount(invoice)
    if paid >= invoice.amount - 0.005:
        return "PAID"
    return "PARTIALLY_PAID" if paid > 0 else "AWAITING_FUNDS"


def _apply_status(db: Session, part: PayoutInstallment, response: dict) -> None:
    invoice = part.invoice
    campaign = invoice.campaign
    line = invoice.budget_line
    if response.get("simulated") or (part.paypal_batch_id or "").startswith("SANDBOX-"):
        part.status = "failed"
        invoice.status = "FAILED"
        invoice.ai_summary = (invoice.ai_summary or "") + "\nPayout was simulated; no vendor received funds."
        db.commit()
        audit.log(db, actor="system", action="payout.simulated", campaign_id=invoice.campaign_id,
                  invoice_id=invoice.id, detail={"installment_id": part.id})
        return
    header = response.get("batch_header", {})
    part.paypal_batch_id = header.get("payout_batch_id") or part.paypal_batch_id
    items = response.get("items", [])
    succeeded = bool(items) and all(item.get("transaction_status") == "SUCCESS" for item in items)
    failed = header.get("batch_status") in {"DENIED", "CANCELED"} or any(
        item.get("transaction_status") in {"FAILED", "BLOCKED", "RETURNED", "REFUNDED"} for item in items
    )
    if succeeded and part.status != "success":
        campaign.pool_balance = round(campaign.pool_balance - part.amount, 2)
        line.paid_amount = round(line.paid_amount + part.amount, 2)
        part.status = "success"
        invoice.status = _status(invoice)
    elif failed:
        part.status = "failed"
        invoice.status = "FAILED"
    else:
        part.status = "pending"
        invoice.status = "PAYOUT_PENDING"
    db.commit()
    audit.log(db, actor="system", action=f"payout.{part.status}", campaign_id=invoice.campaign_id,
              invoice_id=invoice.id, detail={"installment_id": part.id, "amount": part.amount,
                                             "paypal_batch_id": part.paypal_batch_id})


async def pay_available(db: Session, invoice: Invoice, paypal: PayPalClient) -> None:
    """Reconcile a pending transfer, then send at most the unreserved balance."""
    if not any(v.decision in {"approve", "test_override"} for v in invoice.verifications):
        return
    pending = next((p for p in invoice.installments if p.status == "pending"), None)
    if pending:
        if pending.paypal_batch_id:
            try:
                result = await paypal.get_payout_status(pending.paypal_batch_id)
                _apply_status(db, pending, result)
            except PayPalError:
                return
        else:
            # Reuse the exact sender_batch_id when a previous response was lost.
            await _send_part(db, pending, paypal)
        if pending.status == "pending":
            return
    if invoice.status == "FAILED":
        return
    campaign = db.query(Campaign).filter_by(id=invoice.campaign_id).with_for_update().one()
    reserved = db.query(func.coalesce(func.sum(PayoutInstallment.amount), 0.0)).join(Invoice).filter(
        Invoice.campaign_id == campaign.id, PayoutInstallment.status == "pending"
    ).scalar()
    remaining = round(invoice.amount - paid_amount(invoice), 2)
    available = round(campaign.pool_balance - float(reserved), 2)
    amount = min(remaining, available)
    if amount < 0.01:
        invoice.status = _status(invoice)
        db.commit()
        return
    vendor = db.get(Vendor, invoice.vendor_id)
    test_override = any(v.decision == "test_override" for v in invoice.verifications)
    if vendor is None or (not test_override and vendor.status != "active") or vendor.payout_email.casefold() != invoice.payout_email.casefold():
        invoice.status = "FAILED"
        db.commit()
        return
    part = PayoutInstallment(invoice_id=invoice.id, amount=amount, currency=invoice.currency,
                             sender_batch_id=f"pending-{invoice.id}-{len(invoice.installments) + 1}")
    db.add(part)
    db.flush()
    part.sender_batch_id = f"straightmoney-installment-{part.id}"
    invoice.status = "PAYOUT_PENDING"
    db.commit()
    audit.log(db, actor="system", action="payout.installment_pending", campaign_id=invoice.campaign_id,
              invoice_id=invoice.id, detail={"installment_id": part.id, "amount": amount})
    await _send_part(db, part, paypal)


async def _send_part(db: Session, part: PayoutInstallment, paypal: PayPalClient) -> None:
    invoice = part.invoice
    vendor = invoice.vendor
    try:
        result = await paypal.create_payout(invoice_id=invoice.id, installment_id=part.id,
            amount=part.amount, currency=invoice.currency, payout_email=invoice.payout_email, vendor_name=vendor.name)
        part.paypal_batch_id = result.get("batch_header", {}).get("payout_batch_id")
        _apply_status(db, part, result)
        if part.status == "pending" and part.paypal_batch_id:
            _apply_status(db, part, await paypal.get_payout_status(part.paypal_batch_id))
    except PayPalError as exc:
        # A network error may follow an accepted request. Keep its idempotency key reserved.
        if exc.status_code == 503 and part.paypal_batch_id is None:
            invoice.ai_summary = (invoice.ai_summary or "") + "\nPayout status uncertain; check PayPal before retrying."
        else:
            part.status = "failed"
            invoice.status = "FAILED"
            payout_unavailable = exc.status_code == 403 and isinstance(exc.body, dict) and exc.body.get("name") == "PAYOUT_NOT_AVAILABLE"
            message = (
                "PayPal Payouts are unavailable for this sandbox sender account's country. "
                "No funds were sent. Use a Payouts-enabled sandbox Business account "
                "from a supported sending country before retrying."
                if payout_unavailable else f"Payout failed: {exc}"
            )
            invoice.ai_summary = (invoice.ai_summary or "") + f"\n{message}"
        db.commit()
        audit.log(db, actor="system", action="payout.request_error", campaign_id=invoice.campaign_id,
                  invoice_id=invoice.id, detail={"installment_id": part.id, "error": str(exc)})


async def pay_campaign(db: Session, campaign_id: int, paypal: PayPalClient) -> None:
    invoices = db.query(Invoice).filter(Invoice.campaign_id == campaign_id,
        Invoice.status.in_(["AWAITING_FUNDS", "PARTIALLY_PAID", "PAYOUT_PENDING"])).order_by(Invoice.id).all()
    for invoice in invoices:
        if any(v.decision == "test_override" for v in invoice.verifications):
            continue  # Test payouts are initiated only by the verifier's explicit action.
        await pay_available(db, invoice, paypal)
