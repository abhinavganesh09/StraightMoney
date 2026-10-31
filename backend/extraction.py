"""
extraction.py — LLM-powered invoice data extraction using Google GenAI SDK (`google.genai`).
"""

from __future__ import annotations

import asyncio
import json
import os
import re
from pathlib import Path
from typing import Optional

import pdfplumber
from google import genai
from google.genai import types
import httpx

from config import settings
from schemas import ExtractionResult


def _get_client() -> genai.Client:
    """Return an authenticated GenAI client instance."""
    api_key = settings.llm_api_key or os.environ.get("GEMINI_API_KEY") or ""
    return genai.Client(api_key=api_key, http_options=types.HttpOptions(
        timeout=60000, retry_options=types.HttpRetryOptions(attempts=1)
    ))


class ExtractionError(Exception):
    """Raised when the LLM fails to produce a valid ExtractionResult."""


# ---------------------------------------------------------------------------
# Prompt helpers
# ---------------------------------------------------------------------------

_EXTRACTION_SCHEMA = """{
  "vendor_name": "string",
  "payout_email": "string (email address of payee, empty string if not found)",
  "invoice_number": "string",
  "amount": number,
  "currency": "string (3-letter ISO code, e.g. USD)",
  "description": "string (what the invoice is for)",
  "line_items": [
    {"description": "string", "amount": number}
  ]
}"""

_TEXT_PROMPT_TEMPLATE = """You are an invoice data-extraction assistant.
Extract the following fields from the invoice text below and return ONLY a
valid JSON object matching the schema.  Do NOT guess or hallucinate missing
fields — use an empty string or 0 for truly missing data.

Required JSON schema:
{schema}

Invoice text:
\"\"\"
{text}
\"\"\"

Return only the JSON object, no markdown fences, no commentary."""

_IMAGE_PROMPT = f"""You are an invoice data-extraction assistant.
Extract the following fields from this invoice image and return ONLY a
valid JSON object matching the schema.  Do NOT guess or hallucinate missing
fields — use an empty string or 0 for truly missing data.

Required JSON schema:
{_EXTRACTION_SCHEMA}

Return only the JSON object, no markdown fences, no commentary."""


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _clean_json(raw: str) -> str:
    """Strip markdown fences and surrounding whitespace from LLM output."""
    raw = raw.strip()
    # Remove ```json ... ``` or ``` ... ```
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    return raw.strip()


def _parse_result(raw: str) -> ExtractionResult:
    """Parse cleaned JSON into ExtractionResult; raises ExtractionError on failure."""
    try:
        data = json.loads(_clean_json(raw))
        return ExtractionResult(**data)
    except Exception as exc:
        raise ExtractionError(f"Failed to parse LLM response: {exc}\nRaw response: {raw[:500]}") from exc


async def _extract_from_text(text: str, model: Optional[str] = None) -> ExtractionResult:
    """Send extracted PDF text to Gemini and parse the result."""
    client = _get_client()
    prompt = _TEXT_PROMPT_TEMPLATE.format(schema=_EXTRACTION_SCHEMA, text=text[:12_000])
    response = await client.aio.models.generate_content(
        model=model or settings.llm_model,
        contents=prompt,
        config=types.GenerateContentConfig(response_mime_type="application/json"),
    )
    return _parse_result(response.text or "")


async def _extract_from_image(file_path: str, mime_type: str, model: Optional[str] = None) -> ExtractionResult:
    """Send raw image bytes to Gemini vision and parse the result."""
    client = _get_client()
    image_bytes = Path(file_path).read_bytes()
    part = types.Part.from_bytes(data=image_bytes, mime_type=mime_type)
    response = await client.aio.models.generate_content(
        model=model or settings.llm_model,
        contents=[_IMAGE_PROMPT, part],
        config=types.GenerateContentConfig(response_mime_type="application/json"),
    )
    return _parse_result(response.text or "")


def _heuristic_extract(text: str, file_path: str) -> ExtractionResult:
    """Fallback extraction when LLM API key is not configured in .env."""
    amt_match = re.search(r"\$\s*([0-9]+(?:\.[0-9]{2})?)", text)
    amount = float(amt_match.group(1)) if amt_match else 400.0

    inv_match = re.search(r"(?:invoice|inv)\s*(?:#|no\.?|number)?\s*[:\-]?\s*([A-Za-z0-9\-]+)", text, re.I)
    inv_num = inv_match.group(1) if inv_match else Path(file_path).stem

    email_match = re.search(r"[\w\.-]+@[\w\.-]+\.\w+", text)
    email = email_match.group(0) if email_match else ""

    return ExtractionResult(
        vendor_name="Demo Vendor",
        payout_email=email,
        invoice_number=inv_num,
        amount=amount,
        currency="USD",
        description=text[:200].strip() or "Delivered materials",
        line_items=[{"description": "Delivery item", "amount": amount}],
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def extract_invoice(file_path: str, file_mime: str) -> ExtractionResult:
    """
    Extract structured invoice data from a PDF or image file using Gemini.

    For PDFs the text layer is extracted first with pdfplumber; for images
    the raw bytes are sent to the vision API.  On a parse failure the call
    is retried once before raising ExtractionError.
    """
    if not settings.llm_api_key or settings.llm_api_key.startswith("your-"):
        # Heuristic fallback for demo without configured API key
        pages_text = ""
        if file_mime == "application/pdf":
            try:
                with pdfplumber.open(file_path) as pdf:
                    pages_text = "\n".join(page.extract_text() or "" for page in pdf.pages)
            except Exception:
                pass
        return _heuristic_extract(pages_text or Path(file_path).stem, file_path)

    last_error: Optional[Exception] = None

    model = settings.llm_model
    for attempt in range(2):  # try up to twice
        try:
            if file_mime == "application/pdf":
                with pdfplumber.open(file_path) as pdf:
                    pages_text = "\n".join(
                        page.extract_text() or "" for page in pdf.pages
                    )
                if not pages_text.strip():
                    raise ExtractionError(
                        "PDF contains no extractable text. Scanned PDFs are not supported."
                    )
                return await asyncio.wait_for(_extract_from_text(pages_text, model=model), timeout=60)

            elif file_mime.startswith("image/"):
                return await asyncio.wait_for(_extract_from_image(file_path, file_mime, model=model), timeout=60)

            else:
                raise ExtractionError(f"Unsupported MIME type for extraction: {file_mime}")

        except ExtractionError as exc:
            last_error = exc
            if attempt == 0:
                continue  # retry once
            raise

        except Exception as exc:
            last_error = exc
            transient = isinstance(exc, (TimeoutError, httpx.TimeoutException, httpx.NetworkError)) or getattr(exc, "code", None) in {429, 500, 502, 503, 504}
            if attempt == 0 and transient:
                model = settings.llm_fallback_model or settings.llm_model
                await asyncio.sleep(2)
                continue
            if transient:
                raise ExtractionError(
                    "The invoice reading service did not respond after two attempts. "
                    "Your upload was saved for review; please try again shortly."
                ) from exc
            raise ExtractionError(f"Extraction failed: {exc}") from exc

    raise last_error or ExtractionError("Extraction failed after retry.")
