from pydantic import BaseModel, EmailStr
from typing import Optional
from app.core.config import settings


class RegisterRequest(BaseModel):
    email: EmailStr
    username: str
    password: str
    dob: Optional[float]
    gender: Optional[str]
    first_name: Optional[str]
    last_name: Optional[str]
    full_name: Optional[str]
    phone: Optional[str]
    address: Optional[str]
    identity_card: Optional[str]
    identity_card_date: Optional[float]
    identity_card_place: Optional[str]


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenRequest(BaseModel):
    exp: float
    auth_time: float
    sub: str
    typ: Optional[str] = "Bearer"
    email: Optional[EmailStr] = None


class TokenResponse(BaseModel):
    access_token: str
    expires_in: Optional[float] = settings.ACCESS_TOKEN_EXPIRE_SECONDS
    refresh_expires_in: Optional[float] = settings.ACCESS_TOKEN_EXPIRE_SECONDS
    token_type: Optional[str] = "Bearer"
