from typing import Any

from fastapi import APIRouter, Depends
from app.schemas.sche_response import DataResponse
from app.services.srv_auth import AuthService
from app.utils.exception_handler import CustomException, ExceptionType
from app.schemas.sche_auth import LoginRequest, RegisterRequest, TokenResponse
from app.schemas.sche_user import UserBaseResponse

router = APIRouter(tags=["auth"], prefix=f"/auth")


@router.post("/login", response_model=DataResponse[TokenResponse])
def login_basic(form_data: LoginRequest, auth_service: AuthService = Depends()):
    try:
        token = auth_service.login(
            email=form_data.username, password=form_data.password
        )
        return DataResponse(http_code=200, data=token)
    except Exception as e:
        print(e, flush=True)
        raise CustomException(exception=e)


@router.post("/login-keycloak", response_model=DataResponse[TokenResponse])
def login_keycloak(form_data: LoginRequest, auth_service: AuthService = Depends()):
    try:
        data = auth_service.login_keycloak(
            username=form_data.username, password=form_data.password
        )
        if not data:
            raise CustomException(exception=ExceptionType.BAD_REQUEST_DATA_MISMATCH)

        return DataResponse(http_code=200, data=data)
    except Exception as e:
        raise CustomException(exception=e)


@router.post("/register", response_model=DataResponse[UserBaseResponse])
def register(data: RegisterRequest, auth_service: AuthService = Depends()) -> Any:
    try:
        register_user = auth_service.register(data)
        print(register_user.email)
        return DataResponse(http_code=201, data=register_user)
    except Exception as e:
        raise CustomException(exception=e)
