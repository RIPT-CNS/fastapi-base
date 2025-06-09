from fastapi_sqlalchemy import db
from sqlalchemy import or_
from app.models import User
from app.core.security import verify_password, create_access_token, get_password_hash
from app.schemas.sche_auth import RegisterRequest, LoginRequest
from app.schemas.sche_user import UserBaseResponse
from app.schemas.sche_auth import TokenResponse, TokenRequest
from app.utils.exception_handler import CustomException, ExceptionType
from app.core.config import keycloak_openid, settings
from app.utils.enums import UserRole
from app.utils import time_utils


class AuthService(object):
    __instance = None

    @staticmethod
    def login(data: LoginRequest) -> TokenResponse:
        username = data.username
        password = data.password
        if not username or not password:
            raise CustomException(exception=ExceptionType.UNAUTHORIZED)
        user = (
            db.session.query(User)
            .filter(or_(User.username == username, User.email == username))
            .first()
        )
        if not user:
            raise CustomException(exception=ExceptionType.UNAUTHORIZED)
        if not verify_password(password, user.hashed_password):
            raise CustomException(exception=ExceptionType.UNAUTHORIZED)
        elif not user.is_active:
            raise CustomException(exception=ExceptionType.UNAUTHORIZED)

        user.last_login = time_utils.timestamp_now()
        db.session.commit()
        access_token, expire = create_access_token(
            TokenRequest(
                exp=time_utils.timestamp_after_now(
                    seconds=settings.ACCESS_TOKEN_EXPIRE_SECONDS
                ),
                auth_time=time_utils.timestamp_now(),
                sub=str(user.id),
                typ="Bearer",
                email=user.email if user.email else None,
            )
        )
        res_token = TokenResponse(
            access_token=access_token, expires_in=expire, refresh_expires_in=expire
        )
        return res_token

    @staticmethod
    def login_keycloak(data: LoginRequest) -> TokenResponse:
        try:
            username = data.username
            password = data.password
            if not username or not password:
                raise CustomException(exception=ExceptionType.UNAUTHORIZED)
            token = keycloak_openid.token(username, password)
            res_token = TokenResponse(**token)
            return res_token
        except Exception:
            return None

    @staticmethod
    def register(data: RegisterRequest) -> UserBaseResponse:
        exist_user = db.session.query(User).filter(User.email == data.email).first()
        if exist_user:
            raise CustomException(exception=ExceptionType.CONFLICT)
        register_user = User(
            **data.model_dump(exclude={"password"}),
            hashed_password=get_password_hash(data.password),
            roles=[UserRole.USER.name],
            is_active=True,
            last_login=time_utils.timestamp_now(),
        )
        db.session.add(register_user)
        db.session.commit()
        return UserBaseResponse.model_validate(register_user, from_attributes=True)
