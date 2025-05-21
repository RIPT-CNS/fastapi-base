from typing import Optional, TypeVar, Generic
from fastapi import status
from pydantic import BaseModel

T = TypeVar("T")


class MetadataResponse(BaseModel):
    page: int
    page_size: int
    total: int


class BaseResponse(BaseModel):
    __abstract__ = True

    http_code: Optional[int] = status.HTTP_200_OK
    success: Optional[bool] = True
    message: Optional[str] = None
    metadata: Optional[MetadataResponse] = None

    def __init__(
        self,
        http_code: Optional[int] = status.HTTP_200_OK,
        message: Optional[str] = None,
        metadata: Optional[MetadataResponse] = None,
        **kwargs,
    ):
        print(f"========== BaseResponse ==========", flush=True)
        super().__init__(**kwargs)
        self.http_code = http_code
        self.success = True if http_code < status.HTTP_400_BAD_REQUEST else False
        self.message = message
        self.metadata = metadata


class DataResponse(BaseResponse, BaseModel, Generic[T]):
    data: Optional[T] = None

    class Config:
        arbitrary_types_allowed = True

    def __init__(
        self,
        http_code: Optional[int] = status.HTTP_200_OK,
        message: Optional[str] = None,
        data: Optional[T] = None,
        **kwargs,
    ):
        print(f"========== DataResponse ==========", flush=True)
        super().__init__(http_code, message, **kwargs)
        self.http_code = http_code
        self.success = True if http_code < status.HTTP_400_BAD_REQUEST else False
        self.message = message
        self.data = data
