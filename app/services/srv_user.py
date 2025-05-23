from fastapi_sqlalchemy import db
from app.models import User
from app.services.srv_base import BaseService
from app.core.config import settings
from app.core.security import decode_jwt, get_password_hash
from app.schemas.sche_auth import TokenRequest
from app.schemas.sche_user import UserCreateRequest
from app.utils.exception_handler import CustomException, ExceptionType
from app.core.config import keycloak_openid
from google.oauth2 import id_token
from google.auth.transport import requests


class UserService(BaseService[User]):

    def __init__(self):
        super().__init__(User)

    @staticmethod
    def get_me(access_token: str) -> User:
        try:
            try:
                user_info = keycloak_openid.userinfo(access_token)
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
                        access_token,
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
                        payload = decode_jwt(access_token)
                        token_data = TokenRequest(**payload)
                        user = db.session.query(User).get(token_data.sub)
                        print("============ BASIC USER ============")
                        if not user:
                            raise CustomException(exception=ExceptionType.UNAUTHORIZED)
                        return user
                    except:
                        raise CustomException(exception=ExceptionType.UNAUTHORIZED)
        except Exception as e:
            raise CustomException(exception=ExceptionType.UNAUTHORIZED)

    def create(self, data: UserCreateRequest) -> User:
        try:
            origin_password = data.password
            hashed_password = get_password_hash(origin_password)
            processed_data = data.model_dump(exclude_unset=True)
            del processed_data["password"]
            processed_data["hashed_password"] = hashed_password
            return super().create(processed_data)
        except Exception as e:
            raise CustomException(exception=ExceptionType.INTERNAL_SERVER_ERROR)
