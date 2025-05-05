import logging
from typing import Any

from fastapi import APIRouter, Depends
from fastapi_sqlalchemy import db

from app.helpers.exception_handler import CustomException
from app.helpers.login_manager import PermissionRequired, AuthenticateRequired
from app.helpers.paging import Page, PaginationParams, paginate
from app.schemas.sche_base import DataResponse
from app.schemas.sche_user import (
    UserItemResponse,
    UserCreateRequest,
    UserUpdateMeRequest,
    UserUpdateRequest,
)
from app.services.srv_user import UserService
from app.models import User

logger = logging.getLogger()
router = APIRouter()


@router.get(
    "",
    dependencies=[Depends(AuthenticateRequired())],
    response_model=Page[UserItemResponse],
)
def get(params: PaginationParams = Depends()) -> Any:
    """
    API Get list User
    """
    try:
        _query = db.session.query(User)
        users = paginate(model=User, query=_query, params=params)
        return users
    except Exception as e:
        return CustomException(exception=e)


@router.post(
    "",
    dependencies=[Depends(PermissionRequired("admin"))],
    response_model=DataResponse[UserItemResponse],
)
def create(user_data: UserCreateRequest, user_service: UserService = Depends()) -> Any:
    """
    API Create User
    """
    try:
        new_user = user_service.create_user(user_data)
        return DataResponse(http_code=201, data=new_user)
    except Exception as e:
        raise CustomException(exception=e)


@router.get(
    "/me",
    dependencies=[Depends(AuthenticateRequired())],
    response_model=DataResponse[UserItemResponse],
)
def detail_me(
    current_user: User = Depends(UserService.get_current_user),
) -> DataResponse[UserItemResponse]:
    """
    API get detail current User
    """
    try:
        return DataResponse(
            http_code=200, data=UserItemResponse.model_validate(current_user)
        )
    except Exception as e:
        raise CustomException(exception=e)


@router.put(
    "/me",
    dependencies=[Depends(AuthenticateRequired())],
    response_model=DataResponse[UserItemResponse],
)
def update_me(
    user_data: UserUpdateMeRequest,
    current_user: User = Depends(UserService.get_current_user),
    user_service: UserService = Depends(),
) -> DataResponse[UserItemResponse]:
    """
    API Update current User
    """
    # try:
    updated_user = user_service.update_me(data=user_data, current_user=current_user)
    return DataResponse(http_code=200, data=updated_user)
    # except Exception as e:
    #     raise CustomException(exception=e)


@router.get(
    "/{user_id}",
    dependencies=[Depends(AuthenticateRequired())],
    response_model=DataResponse[UserItemResponse],
)
def detail(user_id: int, user_service: UserService = Depends()) -> Any:
    """
    API get Detail User
    """
    try:
        return DataResponse(http_code=200, data=user_service.get(user_id))
    except Exception as e:
        raise CustomException(exception=e)


@router.put(
    "/{user_id}",
    dependencies=[Depends(PermissionRequired("admin"))],
    response_model=DataResponse[UserItemResponse],
)
def update(
    user_id: int, user_data: UserUpdateRequest, user_service: UserService = Depends()
) -> Any:
    """
    API update User
    """
    try:
        updated_user = user_service.update(user_id=user_id, data=user_data)
        return DataResponse(http_code=200, data=updated_user)
    except Exception as e:
        raise CustomException(exception=e)
