from typing import Any

import pytest
from pydantic import ValidationError

from app.core.config import DEV_JWT_PLACEHOLDER, Settings

NEON_URL = "postgresql://app:s3cr3t@ep-x-123.eu-central-1.aws.neon.tech/neondb?sslmode=require"
VALID_PRODUCTION: dict[str, Any] = {
    "environment": "production",
    "DATABASE_URL": NEON_URL,
    "jwt_secret_key": "k" * 48,
    "origin_secret": "o" * 48,
    "allowed_origins": "https://mystocks.vercel.app",
    "finnhub_api_key": "fh-key",
}


def make(**overrides: Any) -> Settings:
    # _env_file=None so a developer's local .env can't leak into these tests.
    return Settings(_env_file=None, **{**VALID_PRODUCTION, **overrides})  # type: ignore[call-arg]


def test_complete_production_config_is_accepted() -> None:
    settings = make()
    assert settings.is_production
    assert settings.allowed_origin_list == ["https://mystocks.vercel.app"]


@pytest.mark.parametrize(
    ("override", "message"),
    [
        ({"DATABASE_URL": None}, "DATABASE_URL"),
        ({"jwt_secret_key": DEV_JWT_PLACEHOLDER}, "placeholder"),
        ({"origin_secret": None}, "ORIGIN_SECRET"),
        ({"origin_secret": "short"}, "ORIGIN_SECRET"),
        ({"allowed_origins": " , "}, "ALLOWED_ORIGINS"),
        ({"finnhub_api_key": None}, "FINNHUB_API_KEY"),
        ({"cookie_secure": False}, "COOKIE_SECURE"),
    ],
)
def test_missing_or_unsafe_production_settings_fail_fast(
    override: dict[str, Any], message: str
) -> None:
    with pytest.raises(ValidationError, match=message):
        make(**override)


def test_all_problems_are_reported_together() -> None:
    with pytest.raises(ValidationError) as exc:
        make(**{"DATABASE_URL": None, "origin_secret": None, "finnhub_api_key": None})
    text = str(exc.value)
    assert all(name in text for name in ("DATABASE_URL", "ORIGIN_SECRET", "FINNHUB_API_KEY"))


def test_short_jwt_secret_is_rejected_in_any_environment() -> None:
    with pytest.raises(ValidationError):
        make(environment="development", jwt_secret_key="too-short")


def test_development_needs_none_of_the_production_settings() -> None:
    settings = Settings(_env_file=None, jwt_secret_key="d" * 40)  # type: ignore[call-arg]
    assert not settings.is_production


def test_neon_url_gets_the_psycopg_driver_and_keeps_sslmode() -> None:
    url = make().database_url
    assert url.startswith("postgresql+psycopg://app:s3cr3t@ep-x-123")
    assert url.endswith("/neondb?sslmode=require")


def test_allowed_origins_are_trimmed() -> None:
    settings = make(allowed_origins=" https://a.vercel.app/ , https://b.example ")
    assert settings.allowed_origin_list == ["https://a.vercel.app", "https://b.example"]


def test_configuration_errors_never_echo_secret_values() -> None:
    # Startup errors land in platform logs; a failed validation must not leak what it was given.
    with pytest.raises(ValidationError) as exc:
        make(
            origin_secret=None,
            jwt_secret_key=DEV_JWT_PLACEHOLDER,
            DATABASE_URL="postgresql://app:LEAKME-db-password@host/db",
            finnhub_api_key="LEAKME-finnhub",
        )
    assert "LEAKME" not in str(exc.value)
    assert "input_value" not in str(exc.value)
