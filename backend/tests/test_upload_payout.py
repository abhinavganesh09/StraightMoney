from types import SimpleNamespace as NS
from unittest.mock import AsyncMock
import pytest
import extraction
from main import _record_payout_result
from payments import PayPalError


def records():
    return NS(status="PAYOUT_PENDING", amount=10), NS(status="pending", paypal_batch_id=None, sender_batch_id=None), NS(pool_balance=100), NS(paid_amount=0)


def test_pending_payout_does_not_deduct_money():
    inv, payout, pool, line = records()
    _record_payout_result(inv, payout, pool, line, {"batch_header": {"payout_batch_id": "batch", "batch_status": "SUCCESS"}, "items": [{"transaction_status": "UNCLAIMED"}]})
    assert inv.status == "PAYOUT_PENDING"
    assert pool.pool_balance == 100


def test_confirmed_payout_deducts_once():
    inv, payout, pool, line = records()
    response = {"items": [{"transaction_status": "SUCCESS"}]}
    _record_payout_result(inv, payout, pool, line, response)
    _record_payout_result(inv, payout, pool, line, response)
    assert inv.status == "PAID"
    assert pool.pool_balance == 90
    assert line.paid_amount == 10


def test_simulation_cannot_be_recorded_as_paid():
    inv, payout, pool, line = records()
    with pytest.raises(PayPalError):
        _record_payout_result(inv, payout, pool, line, {"simulated": True})
    assert pool.pool_balance == 100


@pytest.mark.asyncio
async def test_extraction_awaits_async_sdk(monkeypatch):
    generate = AsyncMock(return_value=NS(text='{"vendor_name":"Vendor","payout_email":"v@example.com","invoice_number":"1","amount":10,"currency":"USD","description":"Books","line_items":[]}'))
    monkeypatch.setattr(extraction, "_get_client", lambda: NS(aio=NS(models=NS(generate_content=generate))))
    result = await extraction._extract_from_text("Invoice")
    assert result.amount == 10
    generate.assert_awaited_once()


class DeadlineError(Exception):
    code = 504


@pytest.mark.asyncio
async def test_deadline_retries_then_recovers(monkeypatch):
    monkeypatch.setattr(extraction.settings, "llm_api_key", "test-key")
    expected = NS(amount=10)
    extract = AsyncMock(side_effect=[DeadlineError("deadline"), expected])
    sleep = AsyncMock()
    monkeypatch.setattr(extraction, "_extract_from_image", extract)
    monkeypatch.setattr(extraction.asyncio, "sleep", sleep)
    assert await extraction.extract_invoice("invoice.png", "image/png") is expected
    assert extract.await_count == 2
    sleep.assert_awaited_once_with(2)
    assert extract.await_args_list[1].kwargs["model"] == extraction.settings.llm_fallback_model


@pytest.mark.asyncio
async def test_repeated_deadline_returns_useful_error(monkeypatch):
    monkeypatch.setattr(extraction.settings, "llm_api_key", "test-key")
    extract = AsyncMock(side_effect=DeadlineError("deadline"))
    monkeypatch.setattr(extraction, "_extract_from_image", extract)
    monkeypatch.setattr(extraction.asyncio, "sleep", AsyncMock())
    with pytest.raises(extraction.ExtractionError, match="two attempts"):
        await extraction.extract_invoice("invoice.png", "image/png")
    assert extract.await_count == 2


@pytest.mark.asyncio
async def test_nontransient_error_is_not_retried(monkeypatch):
    monkeypatch.setattr(extraction.settings, "llm_api_key", "test-key")
    extract = AsyncMock(side_effect=ValueError("invalid configuration"))
    monkeypatch.setattr(extraction, "_extract_from_image", extract)
    with pytest.raises(extraction.ExtractionError, match="invalid configuration"):
        await extraction.extract_invoice("invoice.png", "image/png")
    assert extract.await_count == 1


def test_gemini_has_sixty_second_deadline_and_no_nested_retries(monkeypatch):
    from unittest.mock import Mock
    factory = Mock()
    monkeypatch.setattr(extraction.genai, "Client", factory)
    extraction._get_client()
    options = factory.call_args.kwargs["http_options"]
    assert options.timeout == 60000
    assert options.retry_options.attempts == 1
