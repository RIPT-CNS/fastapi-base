from typing import Annotated, Any

from fastapi import APIRouter, Depends, status
from fastapi.security import OAuth2PasswordRequestForm

from app.schemas.sche_auth import (
    ChangePasswordRequest,
    LoginRequest,
    RefreshTokenRequest,
    RegisterRequest,
    TokenResponse,
)
from app.schemas.sche_response import BaseResponse, DataResponse
from app.schemas.sche_user import UserBaseResponse, UserMeResponse, UserUpdateMeRequest
from app.services.srv_auth import AuthService
from app.services.srv_user import UserService
from app.utils.login_manager import CurrentUser

router = APIRouter(prefix="/auth")

AuthServiceDep = Annotated[AuthService, Depends()]


@router.post("/login", response_model=DataResponse[TokenResponse])
def login(payload: LoginRequest, auth_service: AuthServiceDep) -> Any:
    """Local account login (username or email + password)."""
    return DataResponse(data=auth_service.login(payload.username, payload.password))


@router.post("/token", response_model=TokenResponse)
def login_form(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()], auth_service: AuthServiceDep
) -> Any:
    """OAuth2 password flow (form data, plain token response) used by Swagger "Authorize"."""
    return auth_service.login(form_data.username, form_data.password)


@router.post("/refresh", response_model=DataResponse[TokenResponse])
def refresh(payload: RefreshTokenRequest, auth_service: AuthServiceDep) -> Any:
    return DataResponse(data=auth_service.refresh(payload.refresh_token))


@router.post(
    "/register",
    status_code=status.HTTP_201_CREATED,
    response_model=DataResponse[UserBaseResponse],
)
def register(payload: RegisterRequest, auth_service: AuthServiceDep) -> Any:
    user = auth_service.register(payload)
    return DataResponse(
        http_code=status.HTTP_201_CREATED, data=UserBaseResponse.model_validate(user)
    )


def _me_response(user: CurrentUser) -> UserMeResponse:
    response = UserMeResponse.model_validate(user)
    response.roles = sorted(user.all_roles)
    return response


@router.get("/me", response_model=DataResponse[UserMeResponse])
def get_me(user: CurrentUser) -> Any:
    return DataResponse(data=_me_response(user))


@router.patch("/me", response_model=DataResponse[UserMeResponse])
def update_me(
    payload: UserUpdateMeRequest,
    user: CurrentUser,
    user_service: Annotated[UserService, Depends()],
) -> Any:
    user_service.update(user, payload, partial=True)
    return DataResponse(data=_me_response(user))


@router.post("/change-password", response_model=DataResponse[TokenResponse])
def change_password(
    payload: ChangePasswordRequest, user: CurrentUser, auth_service: AuthServiceDep
) -> Any:
    """Changes the password and revokes all other sessions. Returns fresh tokens."""
    tokens = auth_service.change_password(user, payload.current_password, payload.new_password)
    return DataResponse(data=tokens)


@router.post("/logout", response_model=BaseResponse)
def logout(user: CurrentUser, auth_service: AuthServiceDep) -> Any:
    """Revokes every local token of the current user (all devices).
    For Keycloak sessions use /auth/sso/logout."""
    auth_service.logout(user)
    return BaseResponse(message="Logged out")
