from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends
from fastapi_sqlalchemy import db

from app.core.security import create_access_token
from app.schemas.sche_base import DataResponse
from app.schemas.sche_token import Token
from app.services.srv_user import UserService
from app.helpers.exception_handler import CustomException
from app.schemas.sche_user import UserItemResponse, UserRegisterRequest, LoginRequest, LoginKeycloakRequest
from app.helpers.exception_handler import ExceptionType

router = APIRouter()


@router.post("/login", response_model=DataResponse[Token])
def login_access_token(form_data: LoginRequest, user_service: UserService = Depends()):
    try:
        user = user_service.authenticate(
            email=form_data.username, password=form_data.password
        )
        if not user:
            raise CustomException(exception=ExceptionType.BAD_REQUEST_DATA_MISMATCH)
        elif not user.is_active:
            raise CustomException(exception=ExceptionType.UNAUTHORIZED)

        user.last_login = datetime.now()
        db.session.commit()
        access_token = create_access_token(user_id=user.id)

        return DataResponse(http_code=200, data={"access_token": access_token})
    except Exception as e:
        print(e, flush=True)
        raise CustomException(exception=e)


@router.post("/login-keycloak", response_model=DataResponse[Token])
def login_access_token(form_data: LoginKeycloakRequest, user_service: UserService = Depends()):
    try:
        token = user_service.authenticate_keycloak(
            username=form_data.username, password=form_data.password
        )
        if not token:
            raise CustomException(exception=ExceptionType.BAD_REQUEST_DATA_MISMATCH)

        return DataResponse(http_code=200, data={"access_token": token})
    except Exception as e:
        raise CustomException(exception=e)


@router.post("/register", response_model=DataResponse[UserItemResponse])
def register(
    register_data: UserRegisterRequest, user_service: UserService = Depends()
) -> Any:
    try:
        register_user = user_service.register_user(register_data)
        print(register_user.email)
        return DataResponse(http_code=201, data=register_user)
    except Exception as e:
        raise CustomException(exception=e)
