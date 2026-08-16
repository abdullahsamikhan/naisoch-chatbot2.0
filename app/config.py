"""
Centralized configuration. Everything comes from environment variables
(loaded from .env in local dev via python-dotenv; Railway injects real
env vars in production so the .env file is never needed there).
"""
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

load_dotenv()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Shopify
    shopify_client_id: str
    shopify_client_secret: str
    shopify_shop_domain: str  # e.g. naisoch.myshopify.com
    shopify_api_version: str = "2025-10"

    # Gemini
    gemini_api_key: str
    gemini_chat_model: str = "gemini-2.5-flash-lite"
    gemini_embedding_model: str = "gemini-embedding-001"

    # Admin / security
    admin_sync_secret: str

    # CORS
    allowed_origin: str = "https://naisoch.com.pk"

    # Storage - point this at the Railway persistent volume mount in prod
    data_dir: str = "./data"

    # Rate limiting
    chat_rate_limit: str = "10/minute"

    # Human handoff - phone number the chat can hand off to on WhatsApp,
    # digits only (country code + number, no "+", no spaces) since that's
    # the format wa.me links require. Configurable rather than hardcoded so
    # the number can change without a code deploy.
    whatsapp_number: str = "923404235023"

    @property
    def data_path(self) -> Path:
        p = Path(self.data_dir)
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def token_db_path(self) -> Path:
        return self.data_path / "tokens.db"

    @property
    def catalog_db_path(self) -> Path:
        return self.data_path / "catalog.db"

    @property
    def embeddings_path(self) -> Path:
        return self.data_path / "embeddings.npy"

    @property
    def policies_path(self) -> Path:
        return Path(__file__).parent / "policies" / "policies.json"


@lru_cache
def get_settings() -> Settings:
    return Settings()