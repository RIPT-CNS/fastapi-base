from app.core.crud_router import CRUDRouter
from app.schemas.sche_user import UserBaseResponse, UserCreateRequest, UserUpdateRequest
from app.services.srv_user import UserService

# GET/POST /users, GET/PATCH/DELETE /users/{item_id}
# Requires permissions user:read / user:create / user:update / user:delete (admin has "*")
router = CRUDRouter(
    prefix="/users",
    tags=["Users"],
    service=UserService,
    response_schema=UserBaseResponse,
    create_schema=UserCreateRequest,
    update_schema=UserUpdateRequest,
    permission_prefix="user",
    exclude=("update",),
)
