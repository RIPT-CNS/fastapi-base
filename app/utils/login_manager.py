from fastapi import Depends

from app.models import User
from app.services.srv_user import UserService
from app.utils.exception_handler import CustomException, ExceptionType
from app.core.security import JWTBearer


class AuthenticateRequired:
    def __init__(self, *args):
        self.http_authorization_credentials = None

    def __call__(self, http_authorization_credentials=Depends(JWTBearer())):
        print("========== Authenticate Required ==========", flush=True)
        return UserService().get_me(http_authorization_credentials)


class PermissionRequired:
    def __init__(self, *args):
        self.user = None
        self.permissions = args

    def __call__(self, user: User = Depends(AuthenticateRequired())):
        self.user = user
        if self.user.role not in self.permissions and self.permissions:
            raise CustomException(exception=ExceptionType.FORBIDDEN)
