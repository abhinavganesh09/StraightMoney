"""
donate_test.py — Prove PayPal Orders v2 Sandbox flow.

Flow:
1. Load credentials strictly from .env via python-dotenv.
2. Obtain an OAuth2 token from PayPal Sandbox.
3. Create an Orders v2 order for $10.00 USD.
4. Extract and print the buyer approval link (rel: "approve").
5. Wait for the user to approve the payment in their browser and press Enter.
6. Capture the order and print the final status.

PayPal Developer Documentation Consulted:
- OAuth2 Authentication:
  POST https://api-m.sandbox.paypal.com/v1/oauth2/token
  https://developer.paypal.com/api/rest/authentication/
- Orders v2 Create Order:
  POST https://api-m.sandbox.paypal.com/v2/checkout/orders
  https://developer.paypal.com/docs/api/orders/v2/#orders_create
- Orders v2 Capture Payment:
  POST https://api-m.sandbox.paypal.com/v2/checkout/orders/{id}/capture
  https://developer.paypal.com/docs/api/orders/v2/#orders_capture
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import httpx

# Add backend directory to sys.path so payments module is readily importable
backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from payments import (  # noqa: E402
    PayPalError,
    capture_order,
    create_order,
    get_access_token,
    load_env_credentials,
)


def log(msg: str = "") -> None:
    print(msg, flush=True)


def main() -> int:
    log("=" * 72)
    log("   StraightMoney — PayPal Sandbox Orders v2 Donation Flow Test")
    log("=" * 72)

    # 1. Credentials from .env
    log("\n[Step 1/4] Reading credentials from .env via python-dotenv...")
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

    # 2. OAuth2 Token
    log("[Step 2/4] Requesting OAuth2 client_credentials token from PayPal Sandbox...")
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

    # 3. Create Orders v2 Order for $10 USD
    log("\n[Step 3/4] Creating PayPal Orders v2 Order for $10.00 USD (intent=CAPTURE)...")
    try:
        order = create_order(
            access_token=access_token,
            amount="10.00",
            currency="USD",
            description="StraightMoney $10.00 Donation Test",
            base_url=base_url,
        )
        order_id = order.get("id")
        order_status = order.get("status")
        log(f"  SUCCESS: Order created!")
        log(f"  Order ID : {order_id}")
        log(f"  Status   : {order_status}")

        # Extract approval URL
        approve_url = None
        for link in order.get("links", []):
            if link.get("rel") == "approve":
                approve_url = link.get("href")
                break

        if not approve_url:
            for link in order.get("links", []):
                if link.get("rel") == "payer-action":
                    approve_url = link.get("href")
                    break

        if not approve_url:
            log("  ERROR: Could not find approval URL in PayPal response:")
            log(json.dumps(order, indent=2))
            return 1

        log("\n" + "-" * 72)
        log("   APPROVAL REQUIRED IN BROWSER")
        log("-" * 72)
        log(f"Approval Link:\n{approve_url}")
        log("-" * 72)
        log("Instructions:")
        log("1. Open the approval URL above in your browser.")
        log("2. Log in using your PayPal Sandbox Personal/Buyer account.")
        log("3. Click 'Complete Purchase' / 'Continue' to approve the $10.00 donation.")
        log("-" * 72)

        input("\n>>> Once you have approved the payment in your browser, press [Enter] to capture: ")

    except PayPalError as exc:
        log(f"FAILED to create order:{exc}")
        return 1
    except httpx.RequestError as exc:
        log(f"Network error: {exc}")
        return 1

    # 4. Capture the Order
    log(f"\n[Step 4/4] Capturing payment for order {order_id}...")
    try:
        capture_result = capture_order(access_token=access_token, order_id=order_id, base_url=base_url)
        final_status = capture_result.get("status")
        log(f"  SUCCESS: Order captured successfully!")
        log(f"  Final Status: {final_status}")

        purchase_units = capture_result.get("purchase_units", [])
        if purchase_units:
            captures = purchase_units[0].get("payments", {}).get("captures", [])
            if captures:
                cap = captures[0]
                log(f"  Capture ID  : {cap.get('id')}")
                log(f"  Amount      : {cap.get('amount', {}).get('value')} {cap.get('amount', {}).get('currency_code')}")

        log("\nFull Capture Response:")
        log(json.dumps(capture_result, indent=2))
        log("\n" + "=" * 72)
        log("   Donation test completed successfully!")
        log("=" * 72)
        return 0

    except PayPalError as exc:
        log(f"FAILED to capture order:{exc}")
        return 1
    except httpx.RequestError as exc:
        log(f"Network error: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
