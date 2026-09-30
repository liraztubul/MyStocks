from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Repo-root .env when run from backend/; real env vars (e.g. from compose) take precedence.
    model_config = SettingsConfigDict(env_file=("../.env", ".env"), extra="ignore")

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

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+psycopg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


settings = Settings()
