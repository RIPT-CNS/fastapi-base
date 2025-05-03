from fastapi import Depends

from app.models import User
from app.services.srv_user import UserService
from app.helpers.exception_handler import CustomException, ExceptionType


def login_required(
    http_authorization_credentials=Depends(UserService().reusable_oauth2),
):
    print("========== login_required ==========", flush=True)
    return UserService().get_current_user(http_authorization_credentials)


class PermissionRequired:
    def __init__(self, *args):
        self.user = None
        self.permissions = args

    def __call__(self, user: User = Depends(login_required)):
        self.user = user
        if self.user.role not in self.permissions and self.permissions:
            raise CustomException(exception=ExceptionType.FORBIDDEN)
