from typing import Optional, List
from pydantic import BaseModel, EmailStr
from app.utils.enums import UserRole
from app.schemas.sche_base import BaseModelResponse


class UserBaseRequest(BaseModel):
    password: Optional[str] = None
    dob: Optional[float] = None
    gender: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    full_name: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    identity_card: Optional[str] = None
    identity_card_date: Optional[float] = None
    identity_card_place: Optional[str] = None


class UserCreateRequest(UserBaseRequest):
    username: Optional[str]
    email: EmailStr
    password: str
    is_active: Optional[bool] = True
    roles: List[str] = [
        UserRole.GUEST,
    ]


class UserUpdateRequest(UserBaseRequest):
    is_active: Optional[bool] = True
    roles: Optional[List[str]] = None


class UserUpdateMeRequest(UserBaseRequest):
    pass


class UserBaseResponse(BaseModelResponse):
    sso_key: Optional[str] = None
    username: Optional[str] = None
    email: EmailStr
    dob: Optional[float] = None
    gender: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    full_name: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    identity_card: Optional[str] = None
    identity_card_date: Optional[float] = None
    identity_card_place: Optional[str] = None
    is_active: Optional[bool] = None
    last_login: Optional[float] = None
    roles: List[str]
