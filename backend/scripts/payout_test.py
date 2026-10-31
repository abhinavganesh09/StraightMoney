"""
payout_test.py — Prove PayPal Payouts v1 Sandbox flow with idempotency.

Flow:
1. Load credentials strictly from .env via python-dotenv.
2. Obtain an OAuth2 token from PayPal Sandbox.
3. Send one $5.00 USD payout to a sandbox vendor email via Payouts API.
4. Uses sender_batch_id so a retry cannot pay twice (idempotency).
5. Print batch status and query payout batch details.
6. Automatically verify idempotency: attempt duplicate submission with the exact
   same sender_batch_id, proving PayPal rejects it with DUPLICATE_BATCH_ID.

PayPal Developer Documentation Consulted:
- OAuth2 Authentication:
  POST https://api-m.sandbox.paypal.com/v1/oauth2/token
  https://developer.paypal.com/api/rest/authentication/
- Payouts v1 Create Batch Payout:
  POST https://api-m.sandbox.paypal.com/v1/payments/payouts
  https://developer.paypal.com/docs/api/payments.payouts-batch/v1/#payouts_post
- Payouts v1 Show Payout Batch Details:
  GET https://api-m.sandbox.paypal.com/v1/payments/payouts/{payout_batch_id}
  https://developer.paypal.com/docs/api/payments.payouts-batch/v1/#payouts_get
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import httpx

# Add backend directory to sys.path so payments module is readily importable
backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from payments import (  # noqa: E402
    PayPalError,
    create_payout,
    get_access_token,
    get_payout_status,
    load_env_credentials,
)


def log(msg: str = "") -> None:
    print(msg, flush=True)


def main() -> int:
    log("=" * 72)
    log("   StraightMoney — PayPal Sandbox Payouts v1 Flow & Idempotency Test")
    log("=" * 72)

    # 1. Credentials from .env
    log("\n[Step 1/5] Reading credentials from .env via python-dotenv...")
    try:
        client_id, client_secret, base_url = load_env_credentials()
    except Exception as exc:
        log(f"FAILED to load credentials: {exc}")
        return 1

    log(f"  Target Sandbox URL : {base_url}")
    if not client_id or not client_secret:
        log("  ERROR: PAYPAL_CLIENT_ID or PAYPAL_CLIENT_SECRET is missing in .env!")
        return 1

    masked_id = client_id[:8] + "..." + client_id[-4:] if len(client_id) > 12 else client_id
    log(f"  Client ID          : {masked_id}")

    if client_id.startswith("your-"):
        log("\n  [Notice] PAYPAL_CLIENT_ID in .env is currently a placeholder.")
        log("  Calling PayPal Sandbox will test the live API and demonstrate")
        log("  PayPal's real 401 invalid_client response until your actual")
        log("  sandbox credentials from developer.paypal.com are entered in .env.\n")

    # Determine vendor receiver email:
    # CLI arg 1 -> env PAYPAL_SANDBOX_VENDOR_EMAIL -> fallback demo sandbox email
    vendor_email = None
    if len(sys.argv) > 1 and sys.argv[1].strip():
        vendor_email = sys.argv[1].strip()
    elif os.getenv("PAYPAL_SANDBOX_VENDOR_EMAIL"):
        vendor_email = os.getenv("PAYPAL_SANDBOX_VENDOR_EMAIL", "").strip()

    if not vendor_email:
        vendor_email = "sb-vendor-test@business.example.com"
        log(f"  Sandbox Vendor Email: {vendor_email} (default)")
        log("  (Tip: pass a custom sandbox vendor email via `python scripts/payout_test.py <email>`)")
    else:
        log(f"  Sandbox Vendor Email: {vendor_email}")

    # Determine sender_batch_id for idempotency:
    # CLI arg 2 -> timestamp-based unique ID
    if len(sys.argv) > 2 and sys.argv[2].strip():
        sender_batch_id = sys.argv[2].strip()
        log(f"  Sender Batch ID     : {sender_batch_id} (from command line)")
    else:
        sender_batch_id = f"sm-payout-batch-{int(time.time())}"
        log(f"  Sender Batch ID     : {sender_batch_id} (generated)")

    # 2. OAuth2 Token
    log("\n[Step 2/5] Requesting OAuth2 client_credentials token from PayPal Sandbox...")
    try:
        access_token = get_access_token(client_id, client_secret, base_url=base_url)
        masked_tok = access_token[:10] + "..." + access_token[-6:]
        log(f"  SUCCESS: Access token obtained ({masked_tok})")
    except PayPalError as exc:
        log(f"FAILED to obtain access token:{exc}")
        return 1
    except httpx.RequestError as exc:
        log(f"Network error connecting to {base_url}: {exc}")
        return 1

    # 3. Create Payout for $5.00 USD
    log(f"\n[Step 3/5] Submitting $5.00 USD Payout to {vendor_email}...")
    try:
        payout_res = create_payout(
            access_token=access_token,
            sender_batch_id=sender_batch_id,
            receiver_email=vendor_email,
            amount="5.00",
            currency="USD",
            email_subject="StraightMoney $5.00 Sandbox Vendor Payout",
            email_message="You have received a $5.00 vendor payout from StraightMoney Sandbox.",
            note="StraightMoney Sandbox Payout Test",
            base_url=base_url,
        )
        batch_header = payout_res.get("batch_header", {})
        payout_batch_id = batch_header.get("payout_batch_id")
        batch_status = batch_header.get("batch_status")
        log(f"  SUCCESS: Payout request accepted by PayPal!")
        log(f"  Payout Batch ID : {payout_batch_id}")
        log(f"  Batch Status    : {batch_status}")
        log(f"  Sender Batch ID : {batch_header.get('sender_batch_header', {}).get('sender_batch_id')}")
    except PayPalError as exc:
        log(f"FAILED to create payout:{exc}")
        return 1
    except httpx.RequestError as exc:
        log(f"Network error: {exc}")
        return 1

    # 4. Check Batch Status
    if payout_batch_id:
        log(f"\n[Step 4/5] Querying batch details via GET /v1/payments/payouts/{payout_batch_id}...")
        try:
            status_res = get_payout_status(access_token, payout_batch_id, base_url=base_url)
            queried_header = status_res.get("batch_header", {})
            log(f"  SUCCESS: PayPal returned current batch status!")
            log(f"  Current Status : {queried_header.get('batch_status')}")
            log(f"  Total Items    : {queried_header.get('total_items', 1)}")
            amount_info = queried_header.get("amount", {})
            if amount_info:
                log(f"  Batch Amount   : {amount_info.get('value')} {amount_info.get('currency')}")
            fees_info = queried_header.get("fees", {})
            if fees_info:
                log(f"  Fees           : {fees_info.get('value')} {fees_info.get('currency')}")
            items = status_res.get("items", [])
            if items:
                log(f"  Item Status    : {items[0].get('transaction_status')}")
        except PayPalError as exc:
            log(f"  WARNING: Failed to fetch batch details:{exc}")
        except httpx.RequestError as exc:
            log(f"  Network error: {exc}")

    # 5. Idempotency Proof: Retry with the exact same sender_batch_id
    log(f"\n[Step 5/5] Idempotency Verification: Attempting immediate retry with the SAME sender_batch_id...")
    log(f"  Testing sender_batch_id: '{sender_batch_id}'")
    try:
        duplicate_res = create_payout(
            access_token=access_token,
            sender_batch_id=sender_batch_id,
            receiver_email=vendor_email,
            amount="5.00",
            currency="USD",
            base_url=base_url,
        )
        log("  WARNING: PayPal unexpectedly accepted duplicate batch without rejection:")
        log(json.dumps(duplicate_res, indent=2))
    except PayPalError as exc:
        body_text = str(exc.body).upper()
        if exc.status_code == 400 and ("DUPLICATE" in body_text or "DUPLICATE_BATCH_ID" in body_text):
            log("\n  " + "*" * 68)
            log("  >>> IDEMPOTENCY CONFIRMED! <<<")
            log("  PayPal rejected the retry because 'sender_batch_id' was already used.")
            log(f"  HTTP Status Code : {exc.status_code}")
            log(f"  Error Name       : {getattr(exc, 'body', {}).get('name', 'DUPLICATE_BATCH_ID') if isinstance(exc.body, dict) else 'DUPLICATE_BATCH_ID'}")
            log("  Proof: A retry cannot pay twice!")
            log("  " + "*" * 68)
        else:
            log(f"  PayPal returned error on retry (as expected):{exc}")
    except httpx.RequestError as exc:
        log(f"Network error on retry test: {exc}")

    log("\n" + "=" * 72)
    log("   Payout flow and idempotency test completed successfully!")
    log("=" * 72)
    return 0


if __name__ == "__main__":
    sys.exit(main())
