import jwt

from fastapi import Depends

from app.models import User
from app.services.srv_user import UserService
from app.helpers.exception_handler import CustomException, ExceptionType
from app.helpers.enums import AuthMethod


class AuthenticateRequired:
    def __init__(self, auth_method=AuthMethod.BASIC, *args):
        self.auth_method = auth_method

    def __call__(
        self, http_authorization_credentials=Depends(UserService().reusable_oauth2)
    ):
        print("========== authenticate_required ==========", flush=True)
        return UserService().get_current_user(http_authorization_credentials)


class PermissionRequired:
    def __init__(self, *args):
        self.user = None
        self.permissions = args

    def __call__(self, user: User = Depends(AuthenticateRequired())):
        self.user = user
        if self.user.role not in self.permissions and self.permissions:
            raise CustomException(exception=ExceptionType.FORBIDDEN)
