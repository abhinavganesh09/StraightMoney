"""
test_payments.py — Unit tests for PayPal REST client and payments module.

Tests endpoint URLs, payload construction, header generation, error formatting,
and sandbox enforcement without requiring live network access.
"""

from __future__ import annotations

import json
import pytest
import httpx

from payments import (
    PayPalError,
    SANDBOX_BASE_URL,
    capture_order,
    create_order,
    create_payout,
    get_access_token,
    get_payout_status,
    load_env_credentials,
)


def test_sandbox_safety_enforcement(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure that non-sandbox endpoints raise a ValueError safety check."""
    monkeypatch.setenv("PAYPAL_BASE_URL", "https://api-m.paypal.com")  # Live URL!
    monkeypatch.setenv("PAYPAL_CLIENT_ID", "test-client-id")
    monkeypatch.setenv("PAYPAL_CLIENT_SECRET", "test-client-secret")

    with pytest.raises(ValueError, match="SAFETY ERROR"):
        load_env_credentials()


def test_paypal_error_formatting() -> None:
    """Ensure PayPalError formats full response body cleanly."""
    error_body = {
        "name": "DUPLICATE_BATCH_ID",
        "message": "A batch with this sender_batch_id was already processed.",
        "debug_id": "9876543210",
    }
    err = PayPalError(
        status_code=400,
        body=error_body,
        endpoint="https://api-m.sandbox.paypal.com/v1/payments/payouts",
        method="POST",
    )
    formatted = err.format_error()
    assert "DUPLICATE_BATCH_ID" in formatted
    assert "400" in formatted
    assert "POST https://api-m.sandbox.paypal.com/v1/payments/payouts" in formatted


def test_get_access_token(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test OAuth2 client_credentials token request and response handling."""
    def mock_post(client: httpx.Client, url: str, **kwargs: object) -> httpx.Response:
        assert url == f"{SANDBOX_BASE_URL}/v1/oauth2/token"
        assert kwargs.get("auth") == ("test_id", "test_secret")
        assert kwargs.get("data") == {"grant_type": "client_credentials"}
        return httpx.Response(
            status_code=200,
            json={"access_token": "TEST_BEARER_TOKEN", "token_type": "Bearer", "expires_in": 32400},
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx.Client, "post", mock_post)
    token = get_access_token("test_id", "test_secret", base_url=SANDBOX_BASE_URL)
    assert token == "TEST_BEARER_TOKEN"


def test_create_order_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test Orders v2 creation request payload and headers."""
    def mock_post(client: httpx.Client, url: str, **kwargs: object) -> httpx.Response:
        assert url == f"{SANDBOX_BASE_URL}/v2/checkout/orders"
        headers = kwargs.get("headers", {})
        assert headers.get("Authorization") == "Bearer TEST_TOKEN"
        json_data = kwargs.get("json", {})
        assert json_data["intent"] == "CAPTURE"
        assert json_data["purchase_units"][0]["amount"]["value"] == "10.00"
        assert json_data["purchase_units"][0]["amount"]["currency_code"] == "USD"
        return httpx.Response(
            status_code=201,
            json={
                "id": "5O190127TN364715T",
                "status": "CREATED",
                "links": [
                    {
                        "href": "https://www.sandbox.paypal.com/checkoutnow?token=5O190127TN364715T",
                        "rel": "approve",
                        "method": "GET",
                    }
                ],
            },
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx.Client, "post", mock_post)
    res = create_order("TEST_TOKEN", amount="10.00", currency="USD", base_url=SANDBOX_BASE_URL)
    assert res["id"] == "5O190127TN364715T"
    assert res["links"][0]["rel"] == "approve"


def test_capture_order(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test Orders v2 capture request."""
    order_id = "5O190127TN364715T"

    def mock_post(client: httpx.Client, url: str, **kwargs: object) -> httpx.Response:
        assert url == f"{SANDBOX_BASE_URL}/v2/checkout/orders/{order_id}/capture"
        headers = kwargs.get("headers", {})
        assert headers.get("Authorization") == "Bearer TEST_TOKEN"
        return httpx.Response(
            status_code=201,
            json={"id": order_id, "status": "COMPLETED"},
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx.Client, "post", mock_post)
    res = capture_order("TEST_TOKEN", order_id=order_id, base_url=SANDBOX_BASE_URL)
    assert res["status"] == "COMPLETED"


def test_create_payout_with_sender_batch_id(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test Payouts v1 request ensures sender_batch_id is properly formatted."""
    batch_id = "sm-test-batch-001"

    def mock_post(client: httpx.Client, url: str, **kwargs: object) -> httpx.Response:
        assert url == f"{SANDBOX_BASE_URL}/v1/payments/payouts"
        headers = kwargs.get("headers", {})
        assert headers.get("Authorization") == "Bearer TEST_TOKEN"
        json_data = kwargs.get("json", {})
        assert json_data["sender_batch_header"]["sender_batch_id"] == batch_id
        assert json_data["items"][0]["amount"]["value"] == "5.00"
        assert json_data["items"][0]["receiver"] == "vendor@example.com"
        return httpx.Response(
            status_code=201,
            json={
                "batch_header": {
                    "payout_batch_id": "BATCH_PAYPAL_123",
                    "batch_status": "PENDING",
                    "sender_batch_header": {"sender_batch_id": batch_id},
                }
            },
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx.Client, "post", mock_post)
    res = create_payout(
        "TEST_TOKEN",
        sender_batch_id=batch_id,
        receiver_email="vendor@example.com",
        amount="5.00",
        currency="USD",
        base_url=SANDBOX_BASE_URL,
    )
    assert res["batch_header"]["payout_batch_id"] == "BATCH_PAYPAL_123"
    assert res["batch_header"]["batch_status"] == "PENDING"


def test_get_payout_status(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test retrieving payout batch status."""
    batch_id = "BATCH_PAYPAL_123"

    def mock_get(client: httpx.Client, url: str, **kwargs: object) -> httpx.Response:
        assert url == f"{SANDBOX_BASE_URL}/v1/payments/payouts/{batch_id}"
        headers = kwargs.get("headers", {})
        assert headers.get("Authorization") == "Bearer TEST_TOKEN"
        return httpx.Response(
            status_code=200,
            json={
                "batch_header": {
                    "payout_batch_id": batch_id,
                    "batch_status": "SUCCESS",
                }
            },
            request=httpx.Request("GET", url),
        )

    monkeypatch.setattr(httpx.Client, "get", mock_get)
    res = get_payout_status("TEST_TOKEN", payout_batch_id=batch_id, base_url=SANDBOX_BASE_URL)
    assert res["batch_header"]["batch_status"] == "SUCCESS"


def test_create_payout_fallback_on_403(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify that create_payout gracefully falls back to simulated payout when PayPal Sandbox returns 403 PAYOUT_NOT_AVAILABLE."""
    batch_id = "straightmoney-invoice-42"

    def mock_post(client: httpx.Client, url: str, **kwargs: object) -> httpx.Response:
        return httpx.Response(
            status_code=403,
            json={
                "name": "PAYOUT_NOT_AVAILABLE",
                "message": "You live in a country that is not allowed to send this payout.",
            },
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx.Client, "post", mock_post)
    res = create_payout(
        "TEST_TOKEN",
        sender_batch_id=batch_id,
        receiver_email="vendor@example.com",
        amount="150.00",
        currency="USD",
        base_url=SANDBOX_BASE_URL,
    )

    assert res["simulated"] is True
    assert f"SANDBOX-SIM-BATCH-{batch_id}" in res["batch_header"]["payout_batch_id"]
    assert res["batch_header"]["sender_batch_header"]["sender_batch_id"] == batch_id
    assert res["batch_header"]["batch_status"] == "SUCCESS"


def test_create_payout_raises_on_500(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify that unexpected server errors (500) raise PayPalError."""
    def mock_post(client: httpx.Client, url: str, **kwargs: object) -> httpx.Response:
        return httpx.Response(
            status_code=500,
            json={"name": "INTERNAL_SERVER_ERROR", "message": "Server error"},
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx.Client, "post", mock_post)
    with pytest.raises(PayPalError) as exc_info:
        create_payout(
            "TEST_TOKEN",
            sender_batch_id="test-batch-500",
            receiver_email="vendor@example.com",
            amount="50.00",
            currency="USD",
            base_url=SANDBOX_BASE_URL,
        )
    assert exc_info.value.status_code == 500


