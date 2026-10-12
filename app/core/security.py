import uuid
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any

import jwt
from pwdlib import PasswordHash
from pwdlib.hashers.argon2 import Argon2Hasher
from pwdlib.hashers.bcrypt import BcryptHasher

from app.core.config import settings
from app.utils.exception_handler import CustomException, ExceptionType

# New hashes use argon2; bcrypt hashes (from the old passlib base) are still verified
password_hasher = PasswordHash((Argon2Hasher(), BcryptHasher()))
# Used to keep login timing constant when the user does not exist
_DUMMY_HASH = password_hasher.hash("dummy-password")


class TokenType(StrEnum):
    ACCESS = "access"
    REFRESH = "refresh"


def get_password_hash(password: str) -> str:
    return password_hasher.hash(password)


def verify_password(plain_password: str, hashed_password: str | None) -> bool:
    if not hashed_password:
        password_hasher.verify(plain_password, _DUMMY_HASH)
        return False
    try:
        return password_hasher.verify(plain_password, hashed_password)
    except Exception:
        return False


def create_token(
    subject: str,
    token_type: TokenType,
    *,
    version: int = 0,
    expires_minutes: int | None = None,
    extra_claims: dict[str, Any] | None = None,
) -> tuple[str, int]:
    """Return (jwt, lifetime in seconds)."""
    if expires_minutes is None:
        expires_minutes = (
            settings.ACCESS_TOKEN_EXPIRE_MINUTES
            if token_type == TokenType.ACCESS
            else settings.REFRESH_TOKEN_EXPIRE_MINUTES
        )
    now = datetime.now(UTC)
    payload = {
        "iss": settings.jwt_issuer,
        "sub": subject,
        "iat": now,
        "exp": now + timedelta(minutes=expires_minutes),
        "jti": uuid.uuid4().hex,
        "typ": token_type.value,
        "ver": version,
        **(extra_claims or {}),
    }
    token = jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    return token, expires_minutes * 60


def decode_token(token: str, token_type: TokenType) -> dict[str, Any]:
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
            issuer=settings.jwt_issuer,
            options={"require": ["exp", "iat", "sub", "typ"]},
        )
    except jwt.ExpiredSignatureError as e:
        raise CustomException(ExceptionType.UNAUTHORIZED, "Token expired") from e
    except jwt.PyJWTError as e:
        raise CustomException(ExceptionType.UNAUTHORIZED, "Invalid token") from e
    if payload.get("typ") != token_type.value:
        raise CustomException(ExceptionType.UNAUTHORIZED, "Invalid token type")
    return payload


def get_unverified_issuer(token: str) -> str | None:
    """Read `iss` without verifying, only to decide which verifier to use."""
    try:
        return jwt.decode(token, options={"verify_signature": False}).get("iss")
    except jwt.PyJWTError:
        return None
