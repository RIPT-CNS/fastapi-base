"""Tests run against a real PostgreSQL database named <POSTGRES_DB>_test (created automatically).

make test        # or: docker compose run --rm app pytest
"""

import os

os.environ.update(
    {
        "ENVIRONMENT": "test",
        "DEBUG": "false",
        "LOG_LEVEL": "WARNING",
        "DATABASE_URL": "",
        "POSTGRES_DB": f"{os.environ.get('POSTGRES_DB', 'app').removesuffix('_test')}_test",
        "SECRET_KEY": "test-secret-key-0123456789abcdef0123456789",
        "API_PREFIX": "/api",
        "API_VERSION": "v1",
        "AUTH_LOCAL_ENABLED": "true",
        "AUTH_BASIC_ENABLED": "true",
        "AUTH_REGISTRATION_ENABLED": "true",
        "DEFAULT_USER_ROLES": "user",
        "PAGE_SIZE_DEFAULT": "20",
        "PAGE_SIZE_MAX": "100",
        "KEYCLOAK_ENABLED": "true",
        "KEYCLOAK_SERVER_URL": "http://keycloak.internal",
        "KEYCLOAK_PUBLIC_URL": "http://sso.example.test",
        "KEYCLOAK_REALM": "test-realm",
        "KEYCLOAK_CLIENT_ID": "test-backend",
        "KEYCLOAK_CLIENT_SECRET": "test-secret",
        "KEYCLOAK_FRONTEND_CLIENT_ID": "test-frontend",
        "KEYCLOAK_AUDIENCE": "",
        "KEYCLOAK_AUTO_CREATE_USER": "true",
    }
)

import time  # noqa: E402
from collections.abc import Callable, Iterator  # noqa: E402
from types import SimpleNamespace  # noqa: E402

import jwt  # noqa: E402
import pytest  # noqa: E402
from cryptography.hazmat.primitives.asymmetric import rsa  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.engine import make_url  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.core.database import SessionLocal, engine  # noqa: E402
from app.core.keycloak import keycloak_client  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Base, User  # noqa: E402
from app.services.srv_user import UserService  # noqa: E402
from tests.crud_resources import items_router  # noqa: E402

app.include_router(items_router, prefix=settings.API_PREFIX)

PASSWORD = "Password@123"


def _create_test_database() -> None:
    url = make_url(settings.SQLALCHEMY_DATABASE_URI)
    admin_engine = create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin_engine.connect() as conn:
        exists = conn.scalar(
            text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": url.database}
        )
        if not exists:
            conn.execute(text(f'CREATE DATABASE "{url.database}"'))
    admin_engine.dispose()


@pytest.fixture(scope="session", autouse=True)
def database() -> Iterator[None]:
    _create_test_database()
    # Fresh schema every run, including tables of models that no longer exist
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
    Base.metadata.create_all(engine)
    yield
    engine.dispose()


@pytest.fixture(autouse=True)
def clean_tables() -> Iterator[None]:
    yield
    tables = ", ".join(f'"{table.name}"' for table in Base.metadata.sorted_tables)
    with engine.begin() as conn:
        conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client


def create_user(username: str, roles: list[str] | None = None, **values) -> User:
    with SessionLocal() as db:
        return UserService(db).create(
            {
                "username": username,
                "email": f"{username}@example.com",
                "password": PASSWORD,
                "roles": roles if roles is not None else ["user"],
                **values,
            }
        )


def login(client: TestClient, username: str, password: str = PASSWORD) -> dict:
    response = client.post("/api/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200, response.text
    return response.json()["data"]


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def admin_user() -> User:
    return create_user("admin1", roles=["admin"])


@pytest.fixture
def normal_user() -> User:
    return create_user("user1")


@pytest.fixture
def admin_headers(client: TestClient, admin_user: User) -> dict[str, str]:
    return bearer(login(client, admin_user.username)["access_token"])


@pytest.fixture
def user_headers(client: TestClient, normal_user: User) -> dict[str, str]:
    return bearer(login(client, normal_user.username)["access_token"])


@pytest.fixture(scope="session")
def rsa_private_key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture
def kc_token(rsa_private_key, monkeypatch) -> Callable[..., str]:
    """Build Keycloak-like access tokens signed by a test key (no Keycloak server needed)."""
    signing_key = SimpleNamespace(key=rsa_private_key.public_key())
    monkeypatch.setattr(keycloak_client._jwks, "get_signing_key_from_jwt", lambda _: signing_key)

    def make(**overrides) -> str:
        now = int(time.time())
        claims = {
            "iss": keycloak_client.issuer,
            "aud": [keycloak_client.audience, "account"],
            "azp": "test-frontend",
            "typ": "Bearer",
            "sub": "kc-subject-1",
            "iat": now,
            "exp": now + 300,
            "preferred_username": "kc.user",
            "email": "kc.user@example.com",
            "email_verified": True,
            "name": "KC User",
            "given_name": "KC",
            "family_name": "User",
            "realm_access": {"roles": ["user"]},
        }
        claims.update(overrides)
        claims = {key: value for key, value in claims.items() if value is not None}
        return jwt.encode(claims, rsa_private_key, algorithm="RS256", headers={"kid": "test"})

    return make
