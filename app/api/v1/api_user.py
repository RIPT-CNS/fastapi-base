from app.core.base_api import BaseAPI
from app.schemas.sche_user import UserBaseResponse, UserCreateRequest, UserUpdateRequest
from app.services.srv_user import UserService


class UserAPI(BaseAPI):
    """/users: needs user:read / create / update / delete / import / export (admin has "*")."""

    prefix = "/users"
    tags = ["Users"]
    service = UserService
    response_schema = UserBaseResponse
    create_schema = UserCreateRequest
    update_schema = UserUpdateRequest
    import_key = "username"
    permission_prefix = "user"
    # Full replace (PUT) makes no sense for accounts: use PATCH
    disabled_routes = ("update_one", "update_many", "update_all")
