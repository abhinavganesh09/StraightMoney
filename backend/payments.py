"""
payments.py — PayPal REST API client for orders, captures, and payouts.

This is the ONLY module that reads PayPal credentials from .env via python-dotenv.
Strictly configured for PayPal SANDBOX only (https://api-m.sandbox.paypal.com).

Endpoints reference (PayPal Developer Documentation):
- OAuth2 Authentication:
  POST https://api-m.sandbox.paypal.com/v1/oauth2/token
  Doc: https://developer.paypal.com/api/rest/authentication/
- Orders v2 Create:
  POST https://api-m.sandbox.paypal.com/v2/checkout/orders
  Doc: https://developer.paypal.com/docs/api/orders/v2/#orders_create
- Orders v2 Capture:
  POST https://api-m.sandbox.paypal.com/v2/checkout/orders/{id}/capture
  Doc: https://developer.paypal.com/docs/api/orders/v2/#orders_capture
- Payouts v1 Create Batch:
  POST https://api-m.sandbox.paypal.com/v1/payments/payouts
  Doc: https://developer.paypal.com/docs/api/payments.payouts-batch/v1/#payouts_post
- Payouts v1 Show Batch Details:
  GET https://api-m.sandbox.paypal.com/v1/payments/payouts/{payout_batch_id}
  Doc: https://developer.paypal.com/docs/api/payments.payouts-batch/v1/#payouts_get
"""

from __future__ import annotations

import json
import os
import uuid
from pathlib import Path
from typing import Any

import dotenv
import httpx

SANDBOX_BASE_URL: str = "https://api-m.sandbox.paypal.com"


class PayPalError(Exception):
    """Raised when a PayPal API call returns a non-2xx response."""

    def __init__(
        self,
        status_code: int,
        body: Any,
        endpoint: str = "",
        method: str = "",
    ) -> None:
        self.status_code = status_code
        self.body = body
        self.endpoint = endpoint
        self.method = method
        super().__init__(self.format_error())

    def format_error(self) -> str:
        """Format the full PayPal error response for clear console inspection."""
        if isinstance(self.body, dict):
            body_str = json.dumps(self.body, indent=2)
        elif isinstance(self.body, (bytes, bytearray)):
            body_str = self.body.decode(errors="replace")
        else:
            body_str = str(self.body)
        return (
            f"\n--- PayPal API Error [{self.status_code}] ---"
            f"\nMethod / Endpoint: {self.method} {self.endpoint}"
            f"\nStatus Code: {self.status_code}"
            f"\nResponse Body:\n{body_str}"
            f"\n-----------------------------------------------"
        )


def load_env_credentials() -> tuple[str, str, str]:
    """
    Read PayPal credentials strictly from .env via python-dotenv.

    Returns:
        tuple of (client_id, client_secret, base_url)
    """
    root_env = Path(__file__).resolve().parent.parent / ".env"
    if root_env.exists():
        dotenv.load_dotenv(root_env, override=False)

    client_id = os.getenv("PAYPAL_CLIENT_ID", "").strip()
    client_secret = os.getenv("PAYPAL_CLIENT_SECRET", "").strip()
    base_url = os.getenv("PAYPAL_BASE_URL", SANDBOX_BASE_URL).strip().rstrip("/")

    # Strict safety check: SANDBOX ONLY
    if "sandbox" not in base_url.lower():
        raise ValueError(
            f"SAFETY ERROR: Base URL '{base_url}' is not a PayPal Sandbox endpoint. "
            "StraightMoney is configured for PayPal SANDBOX only!"
        )

    return client_id, client_secret, base_url


def _handle_response(resp: httpx.Response, endpoint: str, method: str) -> dict[str, Any]:
    """Parse JSON or raise a structured PayPalError with full response body."""
    if resp.status_code not in (200, 201):
        try:
            body = resp.json()
        except Exception:
            body = resp.text
        raise PayPalError(
            status_code=resp.status_code,
            body=body,
            endpoint=endpoint,
            method=method,
        )
    return resp.json()


# ======================================================================
# Standalone Typed Functions (Synchronous, using httpx.Client)
# ======================================================================

def get_access_token(
    client_id: str,
    client_secret: str,
    base_url: str = SANDBOX_BASE_URL,
) -> str:
    """
    Obtain an OAuth2 Bearer token from PayPal Sandbox via client_credentials grant.

    Endpoint: POST /v1/oauth2/token
    Docs: https://developer.paypal.com/api/rest/authentication/
    """
    url = f"{base_url}/v1/oauth2/token"
    headers = {
        "Accept": "application/json",
        "Accept-Language": "en_US",
    }
    data = {"grant_type": "client_credentials"}

    with httpx.Client(timeout=30.0) as client:
        resp = client.post(
            url,
            auth=(client_id, client_secret),
            headers=headers,
            data=data,
        )

    result = _handle_response(resp, endpoint=url, method="POST")
    return result["access_token"]


def create_order(
    access_token: str,
    amount: str = "10.00",
    currency: str = "USD",
    description: str = "StraightMoney donation",
    custom_id: str | None = None,
    base_url: str = SANDBOX_BASE_URL,
) -> dict[str, Any]:
    """
    Create a PayPal Orders v2 checkout order with CAPTURE intent.

    Endpoint: POST /v2/checkout/orders
    Docs: https://developer.paypal.com/docs/api/orders/v2/#orders_create
    """
    url = f"{base_url}/v2/checkout/orders"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }
    unit: dict[str, Any] = {
        "amount": {
            "currency_code": currency,
            "value": amount,
        },
        "description": description,
    }
    if custom_id:
        unit["custom_id"] = custom_id

    payload = {
        "intent": "CAPTURE",
        "purchase_units": [unit],
        "application_context": {
            "brand_name": "StraightMoney",
            "landing_page": "NO_PREFERENCE",
            "user_action": "PAY_NOW",
            "return_url": os.getenv("FRONTEND_URL", "http://localhost:3000").rstrip("/") + "/",
            "cancel_url": os.getenv("FRONTEND_URL", "http://localhost:3000").rstrip("/") + "/",
        },
    }

    with httpx.Client(timeout=30.0) as client:
        resp = client.post(url, headers=headers, json=payload)

    return _handle_response(resp, endpoint=url, method="POST")


def capture_order(
    access_token: str,
    order_id: str,
    base_url: str = SANDBOX_BASE_URL,
) -> dict[str, Any]:
    """
    Capture payment for an approved PayPal Orders v2 order.

    Endpoint: POST /v2/checkout/orders/{id}/capture
    Docs: https://developer.paypal.com/docs/api/orders/v2/#orders_capture
    """
    url = f"{base_url}/v2/checkout/orders/{order_id}/capture"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }

    with httpx.Client(timeout=30.0) as client:
        resp = client.post(url, headers=headers, json={})

    return _handle_response(resp, endpoint=url, method="POST")


def create_payout(
    access_token: str,
    sender_batch_id: str,
    receiver_email: str,
    amount: str = "5.00",
    currency: str = "USD",
    email_subject: str = "StraightMoney Vendor Payout",
    email_message: str = "You have received a payout from StraightMoney.",
    note: str = "StraightMoney sandbox payout",
    sender_item_id: str | None = None,
    base_url: str = SANDBOX_BASE_URL,
) -> dict[str, Any]:
    """
    Initiate a PayPal Payout to a sandbox vendor email via Payouts API.

    Uses `sender_batch_id` for idempotency to prevent duplicate payouts.
    Endpoint: POST /v1/payments/payouts
    Docs: https://developer.paypal.com/docs/api/payments.payouts-batch/v1/#payouts_post
    """
    url = f"{base_url}/v1/payments/payouts"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }
    payload = {
        "sender_batch_header": {
            "sender_batch_id": sender_batch_id,
            "email_subject": email_subject,
            "email_message": email_message,
        },
        "items": [
            {
                "recipient_type": "EMAIL",
                "amount": {
                    "value": amount,
                    "currency": currency,
                },
                "receiver": receiver_email,
                "note": note,
                "sender_item_id": sender_item_id or sender_batch_id,
            }
        ],
    }

    try:
        with httpx.Client(timeout=30.0) as client:
            resp = client.post(url, headers=headers, json=payload)
        return _handle_response(resp, endpoint=url, method="POST")
    except PayPalError as exc:
        body_str = json.dumps(exc.body) if isinstance(exc.body, (dict, list)) else str(exc.body)
        if exc.status_code == 403 or "PAYOUT_NOT_AVAILABLE" in body_str or "USER_BUSINESS_ACCOUNT_RESTRICTED" in body_str:
            return {
                "batch_header": {
                    "payout_batch_id": f"SANDBOX-SIM-BATCH-{sender_batch_id}",
                    "batch_status": "SUCCESS",
                    "sender_batch_header": {"sender_batch_id": sender_batch_id},
                },
                "simulated": True,
                "simulation_reason": "PayPal Sandbox Payouts restricted for this account (SPEC.md Section 10 fallback)",
            }
        raise

def get_payout_status(
    access_token: str,
    payout_batch_id: str,
    base_url: str = SANDBOX_BASE_URL,
) -> dict[str, Any]:
    """
    Retrieve the current status of a PayPal Payout batch.

    Endpoint: GET /v1/payments/payouts/{payout_batch_id}
    Docs: https://developer.paypal.com/docs/api/payments.payouts-batch/v1/#payouts_get
    """
    url = f"{base_url}/v1/payments/payouts/{payout_batch_id}"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }

    with httpx.Client(timeout=30.0) as client:
        resp = client.get(url, headers=headers)

    return _handle_response(resp, endpoint=url, method="GET")


# ======================================================================
# PayPalClient — Async Interface for FastAPI Backend
# ======================================================================

class PayPalClient:
    """
    Async client for PayPal REST APIs used by FastAPI backend.
    """

    def __init__(self) -> None:
        client_id, client_secret, base_url = load_env_credentials()
        self._base_url = base_url
        self._client_id = client_id
        self._client_secret = client_secret
        self._simulate_payouts = os.getenv("PAYPAL_SIMULATE_PAYOUTS", "").lower() in ("true", "1", "yes")
        self._access_token: str | None = None

    @property
    def is_configured(self) -> bool:
        """Return True when real credentials (not placeholders) are present."""
        return bool(
            self._client_id
            and self._client_secret
            and not self._client_id.startswith("your-")
            and not self._client_secret.startswith("your-")
        )

    async def get_access_token(self) -> str:
        """Obtain an OAuth2 access token asynchronously."""
        url = f"{self._base_url}/v1/oauth2/token"
        headers = {
            "Accept": "application/json",
            "Accept-Language": "en_US",
        }
        data = {"grant_type": "client_credentials"}

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                url,
                auth=(self._client_id, self._client_secret),
                headers=headers,
                data=data,
            )

        result = _handle_response(resp, endpoint=url, method="POST")
        self._access_token = result["access_token"]
        return self._access_token

    async def _auth_headers(self) -> dict[str, str]:
        token = self._access_token or await self.get_access_token()
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

    async def create_order(
        self,
        campaign_id: int,
        amount: float,
        currency: str,
        donor_name: str,
    ) -> dict[str, Any]:
        """Create a PayPal Order for a donor contribution."""
        if not self.is_configured:
            return {
                "id": f"SANDBOX-ORDER-{uuid.uuid4().hex[:10].upper()}",
                "status": "CREATED",
                "simulated": True,
            }

        headers = await self._auth_headers()
        url = f"{self._base_url}/v2/checkout/orders"
        payload = {
            "intent": "CAPTURE",
            "purchase_units": [
                {
                    "custom_id": str(campaign_id),
                    "description": f"Donation to campaign {campaign_id} by {donor_name}",
                    "amount": {
                        "currency_code": currency,
                        "value": f"{amount:.2f}",
                    },
                }
            ],
            "application_context": {
                "brand_name": "StraightMoney",
                "landing_page": "NO_PREFERENCE",
                "user_action": "PAY_NOW",
                "return_url": os.getenv("FRONTEND_URL", "http://localhost:3000").rstrip("/") + "/",
                "cancel_url": os.getenv("FRONTEND_URL", "http://localhost:3000").rstrip("/") + "/",
            },
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(url, headers=headers, json=payload)
            return _handle_response(resp, endpoint=url, method="POST")
        except httpx.RequestError as exc:
            raise PayPalError(503, body={"error": "network_error", "message": str(exc)}, endpoint=url, method="POST") from exc

    async def capture_order(self, order_id: str) -> dict[str, Any]:
        """Capture an approved PayPal Order."""
        if not self.is_configured or order_id.startswith("SANDBOX-"):
            return {
                "id": order_id,
                "status": "COMPLETED",
                "simulated": True,
            }

        headers = await self._auth_headers()
        url = f"{self._base_url}/v2/checkout/orders/{order_id}/capture"

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(url, headers=headers, json={})
            return _handle_response(resp, endpoint=url, method="POST")
        except httpx.RequestError as exc:
            raise PayPalError(503, body={"error": "network_error", "message": str(exc)}, endpoint=url, method="POST") from exc

    async def create_payout(
        self,
        invoice_id: int,
        amount: float,
        currency: str,
        payout_email: str,
        vendor_name: str,
        installment_id: int | None = None,
    ) -> dict[str, Any]:
        """Initiate a PayPal Payout to a vendor's email."""
        # Use deterministic sender_batch_id for idempotency per SPEC.md Section 10
        sender_batch_id = (
            f"straightmoney-installment-{installment_id}"
            if installment_id is not None else f"straightmoney-invoice-{invoice_id}"
        )

        if not self.is_configured or self._simulate_payouts:
            return {
                "batch_header": {
                    "payout_batch_id": f"SANDBOX-BATCH-{uuid.uuid4().hex[:10].upper()}",
                    "batch_status": "SUCCESS",
                    "sender_batch_header": {"sender_batch_id": sender_batch_id},
                },
                "simulated": True,
            }

        headers = await self._auth_headers()
        url = f"{self._base_url}/v1/payments/payouts"
        payload = {
            "sender_batch_header": {
                "sender_batch_id": sender_batch_id,
                "email_subject": "StraightMoney Vendor Payout",
                "email_message": (
                    f"You have received a payout from StraightMoney for invoice #{invoice_id}."
                ),
            },
            "items": [
                {
                    "recipient_type": "EMAIL",
                    "amount": {
                        "value": f"{amount:.2f}",
                        "currency": currency,
                    },
                    "receiver": payout_email,
                    "note": f"StraightMoney payout for invoice #{invoice_id} — {vendor_name}",
                    "sender_item_id": str(installment_id or invoice_id),
                }
            ],
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(url, headers=headers, json=payload)
            return _handle_response(resp, endpoint=url, method="POST")
        except httpx.RequestError as exc:
            raise PayPalError(503, body={"error": "network_error", "message": str(exc)}, endpoint=url, method="POST") from exc

    async def get_payout_status(self, batch_id: str) -> dict[str, Any]:
        """Retrieve the current status of a PayPal Payout batch."""
        if not self.is_configured or self._simulate_payouts or batch_id.startswith("SANDBOX-"):
            return {
                "batch_header": {
                    "payout_batch_id": batch_id,
                    "batch_status": "SUCCESS",
                },
                "items": [{"transaction_status": "SUCCESS"}],
            }

        headers = await self._auth_headers()
        url = f"{self._base_url}/v1/payments/payouts/{batch_id}"

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.get(url, headers=headers)
            return _handle_response(resp, endpoint=url, method="GET")
        except httpx.RequestError as exc:
            raise PayPalError(503, body={"error": "network_error", "message": str(exc)}, endpoint=url, method="GET") from exc
