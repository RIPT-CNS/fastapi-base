from typing import Any, List
from fastapi import APIRouter, Depends, status
from app.utils.exception_handler import CustomException
from app.schemas.sche_response import DataResponse
from app.schemas.sche_base import PaginationParams, SortParams
from app.schemas.sche_user import (
    UserCreateRequest,
    UserUpdateRequest,
    UserBaseResponse,
)
from app.services.srv_user import UserService

router = APIRouter(prefix=f"/users")

user_service: UserService = UserService()


@router.get(
    "/all",
    response_model=DataResponse[List[UserBaseResponse]],
    status_code=status.HTTP_200_OK,
)
def get_all() -> Any:
    try:
        data, metadata = user_service.get_all()
        return DataResponse(http_code=status.HTTP_200_OK, data=data, metadata=metadata)
    except Exception as e:
        return CustomException(exception=e)


@router.get(
    "",
    response_model=DataResponse[List[UserBaseResponse]],
    status_code=status.HTTP_200_OK,
)
def get_by_filter(
    sort_params: SortParams = Depends(),
    pagination_params: PaginationParams = Depends(),
) -> Any:
    try:
        data, metadata = user_service.get_by_filter(
            pagination_params=pagination_params, sort_params=sort_params
        )
        return DataResponse(http_code=status.HTTP_200_OK, data=data, metadata=metadata)
    except Exception as e:
        return CustomException(exception=e)


@router.post(
    "",
    response_model=DataResponse[UserBaseResponse],
    status_code=status.HTTP_201_CREATED,
)
def create(user_data: UserCreateRequest) -> Any:
    try:
        new_user = user_service.create(data=user_data)
        return DataResponse(http_code=status.HTTP_201_CREATED, data=new_user)
    except Exception as e:
        raise CustomException(exception=e)


@router.get(
    "/{user_id}",
    response_model=DataResponse[UserBaseResponse],
    status_code=status.HTTP_200_OK,
)
def get_by_id(user_id: int) -> Any:
    try:
        user = user_service.get_by_id(id=user_id)
        return DataResponse(http_code=status.HTTP_200_OK, data=user)
    except Exception as e:
        raise CustomException(exception=e)


@router.put(
    "/{user_id}",
    response_model=DataResponse[UserBaseResponse],
    status_code=status.HTTP_200_OK,
)
def update_by_id(user_id: int, user_data: UserUpdateRequest) -> Any:
    try:
        updated_user = user_service.update_by_id(id=user_id, data=user_data)
        return DataResponse(http_code=status.HTTP_200_OK, data=updated_user)
    except Exception as e:
        raise CustomException(exception=e)


@router.patch(
    "/{user_id}",
    response_model=DataResponse[UserBaseResponse],
    status_code=status.HTTP_200_OK,
)
def update_by_id(user_id: int, user_data: UserUpdateRequest) -> Any:
    try:
        updated_user = user_service.partial_update_by_id(id=user_id, data=user_data)
        return DataResponse(http_code=status.HTTP_200_OK, data=updated_user)
    except Exception as e:
        raise CustomException(exception=e)


@router.delete(
    "/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_by_id(user_id: int) -> None:
    try:
        user_service.delete_by_id(id=user_id)
    except Exception as e:
        raise CustomException(exception=e)
