import json
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Any

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict
from sqlalchemy.engine import URL

from app.utils.enums import Environment

BASE_DIR = Path(__file__).resolve().parents[2]

# Dev-only default (>= 32 bytes for HS256). Any key containing "change-me" is refused in prod
INSECURE_SECRET_KEY = "change-me-dev-only-secret-key-0123456789"


class Settings(BaseSettings):
    """All config is read from environment variables (or the .env file at project root)."""

    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env", env_file_encoding="utf-8", extra="ignore"
    )

    # ------------------------------------------------------------------ App
    # dev: hot reload, single process. Other values: WEB_CONCURRENCY worker processes
    ENVIRONMENT: Environment = Environment.DEV
    WEB_CONCURRENCY: int = 2
    PROJECT_NAME: str = "FASTAPI_BASE"
    VERSION: str = "1.0.0"
    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"
    LOG_JSON: bool = False
    DOCS_ENABLED: bool = True

    API_PREFIX: str = "/api"
    # Version mounted additionally without version prefix (/api/users == /api/v1/users)
    API_VERSION: str = "v1"
    # Comma separated ("http://a.com,http://b.com") or JSON list
    BACKEND_CORS_ORIGINS: Annotated[list[str], NoDecode] = []

    # ------------------------------------------------------------- Database
    # Full URL overrides POSTGRES_* if set
    DATABASE_URL: str | None = None
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = "postgres"
    POSTGRES_DB: str = "app"
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 20
    DB_ECHO: bool = False

    # ------------------------------------------------ Pagination / BaseAPI
    PAGE_SIZE_DEFAULT: int = 20
    PAGE_SIZE_MAX: int = 100
    # Max rows returned by GET /list and GET /many
    LIST_MAX_ROWS: int = 1000
    # 0 = no limit. Exports are streamed: memory stays flat whatever the size
    EXPORT_MAX_ROWS: int = 0
    # Rows of one import (all are validated in memory before writing). 0 = no limit
    IMPORT_MAX_ROWS: int = 100_000
    IMPORT_MAX_FILE_SIZE_MB: int = 100

    # ----------------------------------------------------- Local auth (JWT)
    SECRET_KEY: str = INSECURE_SECRET_KEY
    JWT_ALGORITHM: str = "HS256"
    JWT_ISSUER: str | None = None
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7
    AUTH_LOCAL_ENABLED: bool = True
    # Accept "Authorization: Basic base64(user:pass)" on every endpoint
    AUTH_BASIC_ENABLED: bool = True
    AUTH_REGISTRATION_ENABLED: bool = True
    DEFAULT_USER_ROLES: Annotated[list[str], NoDecode] = ["user"]

    # Created by `python -m app.cli seed` (run automatically by the migrate service)
    FIRST_SUPERUSER_USERNAME: str = "admin"
    FIRST_SUPERUSER_EMAIL: str | None = "admin@example.com"
    FIRST_SUPERUSER_PASSWORD: str | None = None

    # ------------------------------------------------------- Keycloak (SSO)
    KEYCLOAK_ENABLED: bool = False
    # URL the backend uses to reach Keycloak (token, certs endpoints)
    KEYCLOAK_SERVER_URL: str | None = None
    # URL the browser uses; it is also the token issuer. Defaults to KEYCLOAK_SERVER_URL
    KEYCLOAK_PUBLIC_URL: str | None = None
    KEYCLOAK_REALM: str | None = None
    # Confidential client used by the backend
    KEYCLOAK_CLIENT_ID: str | None = None
    KEYCLOAK_CLIENT_SECRET: str | None = None
    # Public client (PKCE) used by Swagger UI / SPA frontends
    KEYCLOAK_FRONTEND_CLIENT_ID: str | None = None
    # Required "aud" claim of access tokens. Defaults to KEYCLOAK_CLIENT_ID
    KEYCLOAK_AUDIENCE: str | None = None
    KEYCLOAK_VERIFY_SSL: bool = True
    KEYCLOAK_TIMEOUT: float = 10.0
    # Create a local user on first SSO login (just-in-time provisioning)
    KEYCLOAK_AUTO_CREATE_USER: bool = True

    @field_validator("BACKEND_CORS_ORIGINS", "DEFAULT_USER_ROLES", mode="before")
    @classmethod
    def _parse_list(cls, value: Any) -> Any:
        if isinstance(value, str):
            value = value.strip()
            if value.startswith("["):
                return json.loads(value)
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @model_validator(mode="after")
    def _validate(self) -> "Settings":
        if self.KEYCLOAK_ENABLED:
            required = ("KEYCLOAK_SERVER_URL", "KEYCLOAK_REALM", "KEYCLOAK_CLIENT_ID")
            missing = [name for name in required if not getattr(self, name)]
            if missing:
                raise ValueError(f"KEYCLOAK_ENABLED=true but missing: {', '.join(missing)}")
        if self.ENVIRONMENT == Environment.PROD:
            if "change-me" in self.SECRET_KEY or len(self.SECRET_KEY) < 32:
                raise ValueError(
                    "SECRET_KEY must be set to a random value of >= 32 chars in prod "
                    "(openssl rand -hex 32)"
                )
            if self.DEBUG:
                raise ValueError("DEBUG must be false in prod")
        return self

    @property
    def is_prod(self) -> bool:
        return self.ENVIRONMENT == Environment.PROD

    @property
    def jwt_issuer(self) -> str:
        return self.JWT_ISSUER or self.PROJECT_NAME

    @property
    def SQLALCHEMY_DATABASE_URI(self) -> str:
        if self.DATABASE_URL:
            return self.DATABASE_URL
        return URL.create(
            drivername="postgresql+psycopg",
            username=self.POSTGRES_USER,
            password=self.POSTGRES_PASSWORD,
            host=self.POSTGRES_HOST,
            port=self.POSTGRES_PORT,
            database=self.POSTGRES_DB,
        ).render_as_string(hide_password=False)


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
