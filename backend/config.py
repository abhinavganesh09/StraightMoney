"""
config.py — Application configuration loaded from .env via pydantic-settings.
"""

from pathlib import Path

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict


REPO_ENV = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(REPO_ENV)


class Settings(BaseSettings):
    """All environment variables required by StraightMoney backend."""

    # PayPal credentials
    paypal_client_id: str = ""
    paypal_client_secret: str = ""
    paypal_base_url: str = "https://api-m.sandbox.paypal.com"
    paypal_simulate_payouts: bool = False
    enable_verifier_test_override: bool = True  # temporary; sandbox only

    # LLM (Gemini)
    llm_api_key: str = ""
    llm_model: str = "gemini-1.5-flash"
    llm_fallback_model: str = "gemini-3.5-flash-lite"

    # App defaults
    supported_currency: str = "USD"
    database_url: str
    upload_dir: str = "./uploads"
    frontend_url: str = "http://localhost:3000"

    model_config = SettingsConfigDict(extra="ignore")


settings = Settings()
