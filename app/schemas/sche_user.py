from datetime import date, datetime

from pydantic import EmailStr, Field

from app.core.config import settings
from app.schemas.sche_base import BaseModelResponse, BaseSchema

USERNAME_PATTERN = r"^[A-Za-z0-9_.@-]+$"


class UserProfile(BaseSchema):
    full_name: str | None = Field(None, max_length=255)
    first_name: str | None = Field(None, max_length=100)
    last_name: str | None = Field(None, max_length=100)
    dob: date | None = None
    gender: str | None = Field(None, max_length=20)
    phone: str | None = Field(None, max_length=30)
    address: str | None = Field(None, max_length=500)
    identity_card: str | None = Field(None, max_length=50)
    identity_card_date: date | None = None
    identity_card_place: str | None = Field(None, max_length=255)


class UserCreateRequest(UserProfile):
    username: str = Field(min_length=3, max_length=150, pattern=USERNAME_PATTERN)
    email: EmailStr | None = None
    password: str = Field(min_length=8, max_length=128)
    is_active: bool = True
    roles: list[str] = Field(default_factory=lambda: list(settings.DEFAULT_USER_ROLES))


class UserUpdateRequest(UserProfile):
    """Admin update. Every field is optional (PATCH)."""

    email: EmailStr | None = None
    password: str | None = Field(None, min_length=8, max_length=128)
    is_active: bool | None = None
    roles: list[str] | None = None


class UserUpdateMeRequest(UserProfile):
    pass


class UserBaseResponse(UserProfile, BaseModelResponse):
    username: str
    email: EmailStr | None = None
    auth_provider: str
    is_active: bool
    roles: list[str]
    last_login: datetime | None = None


class UserMeResponse(UserBaseResponse):
    """`roles` here are the effective roles: local roles + roles from the SSO token."""
