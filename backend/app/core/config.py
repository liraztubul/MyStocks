from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import make_url

from app.core.emails import normalize_email

# The value .env.example ships with; production must never run with it.
DEV_JWT_PLACEHOLDER = "replace-me-with-a-random-string-of-at-least-32-chars"


class Settings(BaseSettings):
    # Repo-root .env when run from backend/; real env vars (e.g. from compose) take precedence.
    # hide_input_in_errors: a validation error must never echo setting values (secrets) to logs.
    model_config = SettingsConfigDict(
        env_file=("../.env", ".env"), extra="ignore", hide_input_in_errors=True
    )

    environment: Literal["development", "production"] = "development"

    # Production supplies one URL (Neon); local dev and compose build it from parts.
    database_url_override: str | None = Field(default=None, alias="DATABASE_URL")
    postgres_user: str = "mystocks"
    postgres_password: str = "mystocks"
    postgres_db: str = "mystocks"
    postgres_host: str = "localhost"
    postgres_port: int = 5432

    # No default on purpose: the app must refuse to start rather than sign tokens with a known key.
    jwt_secret_key: str = Field(min_length=32)
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    cookie_secure: bool = True

    # Optional so the app still boots without them; stock lookups then report "not configured".
    finnhub_api_key: str | None = None
    coingecko_demo_api_key: str | None = None
    # How long a crypto quote is reused. The Demo plan has a monthly cap (10k calls), so crypto
    # gets a longer cache than stocks (60 s, Finnhub's per-minute limit is the constraint there).
    crypto_quote_ttl_seconds: float = Field(default=300, ge=30)
    market_data_timeout_seconds: float = 5.0

    # Unset: open registration in development, registration disabled in production.
    registration_invite_code: str | None = None
    # Comma-separated emails allowed to see stock market data (quotes and history): the free
    # stock data plans are licensed for personal use only. Unset or empty: everyone in
    # development, nobody in production (the same rule as the invite code). Emails are not
    # verified, so only list addresses that are already registered.
    stock_data_allowed_emails: str | None = None
    # Shared with Vercel, which adds it to every proxied /api request. Unset disables the check.
    origin_secret: str | None = None
    # Comma-separated; state-changing requests from any other Origin are refused when set.
    allowed_origins: str | None = None

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def stock_data_allowlist(self) -> frozenset[str]:
        raw = self.stock_data_allowed_emails or ""
        return frozenset(normalize_email(e) for e in raw.split(",") if e.strip())

    @property
    def database_url(self) -> str:
        if self.database_url_override:
            # Neon hands out postgresql:// URLs; pin the psycopg 3 driver, keep sslmode etc.
            return (
                make_url(self.database_url_override)
                .set(drivername="postgresql+psycopg")
                .render_as_string(hide_password=False)
            )
        return (
            f"postgresql+psycopg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def allowed_origin_list(self) -> list[str]:
        return [o.strip().rstrip("/") for o in (self.allowed_origins or "").split(",") if o.strip()]

    @model_validator(mode="after")
    def _require_production_settings(self) -> "Settings":
        if not self.is_production:
            return self
        problems = []
        if not self.database_url_override:
            problems.append("DATABASE_URL is required")
        if self.jwt_secret_key == DEV_JWT_PLACEHOLDER:
            problems.append("JWT_SECRET_KEY is still the .env.example placeholder")
        if not self.origin_secret or len(self.origin_secret) < 32:
            problems.append("ORIGIN_SECRET must be set (32+ characters)")
        if not self.allowed_origin_list:
            problems.append("ALLOWED_ORIGINS is required")
        if not self.finnhub_api_key:
            problems.append("FINNHUB_API_KEY is required")
        if not self.cookie_secure:
            problems.append("COOKIE_SECURE must be true")
        if problems:
            # Fail at import time, so a misconfigured deploy never starts serving.
            raise ValueError("Invalid production configuration: " + "; ".join(problems))
        return self


settings = Settings()
