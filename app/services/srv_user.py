import jwt

from typing import Optional
from fastapi import Depends
from fastapi.security import HTTPBearer
from fastapi_sqlalchemy import db

from app.models import User
from app.core.config import settings
from app.core.security import verify_password, get_password_hash
from app.schemas.sche_token import TokenPayload
from app.schemas.sche_user import (
    UserCreateRequest,
    UserUpdateMeRequest,
    UserUpdateRequest,
    UserRegisterRequest,
)
from app.schemas.sche_user import UserItemResponse
from app.helpers.exception_handler import CustomException, ExceptionType
from app.core.config import keycloak_openid
from google.oauth2 import id_token
from google.auth.transport import requests


class UserService(object):
    __instance = None

    def __init__(self) -> None:
        pass

    reusable_oauth2 = HTTPBearer(scheme_name="Authorization", auto_error=False)

    @staticmethod
    def authenticate(*, email: str, password: str) -> Optional[User]:
        """
        Check username and password is correct.
        Return object User if correct, else return None
        """
        user = db.session.query(User).filter_by(email=email).first()
        if not user:
            return None
        if not verify_password(password, user.hashed_password):
            return None
        return user

    @staticmethod
    def authenticate_keycloak(*, username: str, password: str) -> Optional[User]:
        try:
            token = keycloak_openid.token(username, password)
            return token["access_token"]
        except Exception:
            return None

    @staticmethod
    def get_current_user(
        http_authorization_credentials=Depends(reusable_oauth2),
    ) -> User:
        try:
            if http_authorization_credentials is None:
                raise CustomException(exception=ExceptionType.UNAUTHORIZED)
            if not http_authorization_credentials.credentials:
                raise CustomException(exception=ExceptionType.UNAUTHORIZED)
            try:
                user_info = keycloak_openid.userinfo(
                    http_authorization_credentials.credentials
                )
                print("============ KEYCLOAK USER ============", user_info)
                if not user_info:
                    raise
                return User(
                    username=user_info["preferred_username"],
                    email=user_info.get("email"),
                    full_name=user_info.get("name"),
                )
            except:
                try:
                    user_info = id_token.verify_oauth2_token(
                        http_authorization_credentials.credentials,
                        requests.Request(),
                        settings.GOOGLE_CLIENT_ID,
                    )
                    print("============ GOOGLE USER ============", user_info)
                    if not user_info:
                        raise
                    return User(
                        username=user_info["sub"],
                        email=user_info.get("email"),
                        full_name=user_info.get("name"),
                    )
                except:
                    try:
                        payload = jwt.decode(
                            http_authorization_credentials.credentials,
                            settings.SECRET_KEY,
                            algorithms=[settings.SECURITY_ALGORITHM],
                        )
                        token_data = TokenPayload(**payload)
                        user = db.session.query(User).get(token_data.user_id)
                        print("============ BASIC USER ============")
                        if not user:
                            raise CustomException(exception=ExceptionType.UNAUTHORIZED)
                    except:
                        raise CustomException(exception=ExceptionType.UNAUTHORIZED)
        except Exception as e:
            raise CustomException(exception=ExceptionType.UNAUTHORIZED)
        return user

    @staticmethod
    def register_user(data: UserRegisterRequest) -> UserItemResponse:
        exist_user = db.session.query(User).filter(User.email == data.email).first()
        if exist_user:
            raise CustomException(exception=ExceptionType.CONFLICT)
        register_user = User(
            full_name=data.full_name,
            email=data.email,
            hashed_password=get_password_hash(data.password),
            is_active=True,
            role=data.role.value,
        )
        print("register_user", register_user)
        db.session.add(register_user)
        db.session.commit()
        return UserItemResponse.model_validate(register_user)

    @staticmethod
    def create_user(data: UserCreateRequest) -> UserItemResponse:
        exist_user = db.session.query(User).filter(User.email == data.email).first()
        if exist_user:
            raise CustomException(exception=ExceptionType.CONFLICT)
        new_user = User(
            full_name=data.full_name,
            email=data.email,
            hashed_password=get_password_hash(data.password),
            is_active=data.is_active,
            role=data.role.value,
        )
        db.session.add(new_user)
        db.session.commit()
        return UserItemResponse.model_validate(new_user)

    @staticmethod
    def update_me(data: UserUpdateMeRequest, current_user: User) -> UserItemResponse:
        if data.email is not None:
            exist_user = (
                db.session.query(User)
                .filter(User.email == data.email, User.id != current_user.id)
                .first()
            )
            if exist_user:
                raise CustomException(exception=ExceptionType.CONFLICT)
        current_user.full_name = (
            current_user.full_name if data.full_name is None else data.full_name
        )
        current_user.email = current_user.email if data.email is None else data.email
        current_user.hashed_password = (
            current_user.hashed_password
            if data.password is None
            else get_password_hash(data.password)
        )
        db.session.commit()
        return UserItemResponse.model_validate(current_user)

    @staticmethod
    def update(user_id: int, data: UserUpdateRequest) -> UserItemResponse:
        user = db.session.query(User).get(user_id)
        if user is None:
            raise CustomException(exception=ExceptionType.NOT_FOUND)
        user.full_name = user.full_name if data.full_name is None else data.full_name
        user.email = user.email if data.email is None else data.email
        user.hashed_password = (
            user.hashed_password
            if data.password is None
            else get_password_hash(data.password)
        )
        user.is_active = user.is_active if data.is_active is None else data.is_active
        user.role = user.role if data.role is None else data.role.value
        db.session.commit()
        return UserItemResponse.model_validate(user)

    @staticmethod
    def get(user_id):
        exist_user = db.session.query(User).get(user_id)
        if exist_user is None:
            raise CustomException(exception=ExceptionType.NOT_FOUND)
        return exist_user
