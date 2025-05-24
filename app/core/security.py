from typing import Tuple, Any

from fastapi import Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
import jwt
from passlib.context import CryptContext

from app.core.config import settings
from app.utils.exception_handler import CustomException, ExceptionType
from app.utils import time_utils
from app.schemas.sche_auth import TokenRequest

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
ALGORITHM = "HS256"


def create_access_token(
    payload: TokenRequest, expires_seconds: int = None
) -> Tuple[str, float]:
    if expires_seconds:
        expire = time_utils.timestamp_after_now(seconds=expires_seconds)
    else:
        expire = time_utils.timestamp_after_now(
            seconds=settings.ACCESS_TOKEN_EXPIRE_SECONDS
        )
    encoded_jwt = jwt.encode(
        payload.model_dump(), settings.SECRET_KEY, algorithm=ALGORITHM
    )
    return encoded_jwt, expire


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


def decode_jwt(token: str) -> dict[str, Any]:
    try:
        decoded_token = jwt.decode(token, settings.SECRET_KEY, algorithms=ALGORITHM)
        if decoded_token["exp"] >= time_utils.timestamp_now():
            return decoded_token
        return None
    except Exception as e:
        return None


class JWTBearer(HTTPBearer):
    def __init__(self, auto_error: bool = True):
        super(JWTBearer, self).__init__(auto_error=auto_error)

    async def __call__(self, request: Request):
        credentials: HTTPAuthorizationCredentials = await super(
            JWTBearer, self
        ).__call__(request)
        if credentials is None:
            raise CustomException(exception=ExceptionType.UNAUTHORIZED)
        if not credentials.credentials:
            raise CustomException(exception=ExceptionType.UNAUTHORIZED)
        if not credentials.scheme == "Bearer":
            raise CustomException(exception=ExceptionType.UNAUTHORIZED)
        if not self.verify_jwt(credentials.credentials):
            raise CustomException(exception=ExceptionType.UNAUTHORIZED)
        return credentials.credentials

    def verify_jwt(self, jwt_token: str) -> bool:
        is_token_valid: bool = False
        try:
            payload = decode_jwt(jwt_token)
        except Exception as e:
            payload = None
        if payload:
            is_token_valid = True
        return is_token_valid
