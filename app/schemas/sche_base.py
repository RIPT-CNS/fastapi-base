from typing import Optional, TypeVar, Generic

from pydantic import BaseModel

T = TypeVar("T")


class BaseResponse(BaseModel):
    __abstract__ = True

    http_code: Optional[int] = 200
    success: Optional[bool] = True
    message: Optional[str] = None

    def __init__(
        self, http_code: Optional[int] = 200, message: Optional[str] = None, **kwargs
    ):
        print(f"========== BaseResponse ==========", flush=True)
        super().__init__(**kwargs)
        self.http_code = http_code
        self.success = True if http_code < 400 else False
        self.message = message


class DataResponse(BaseResponse, BaseModel, Generic[T]):
    data: Optional[T] = None

    class Config:
        arbitrary_types_allowed = True

    def __init__(
        self,
        http_code: Optional[int] = 200,
        message: Optional[str] = None,
        data: Optional[T] = None,
        **kwargs,
    ):
        print(f"========== DataResponse ==========", flush=True)
        super().__init__(http_code, message, **kwargs)
        self.http_code = http_code
        self.success = True if http_code < 400 else False
        self.message = message
        self.data = data


class MetadataSchema(BaseModel):
    current_page: int
    page_size: int
    total: int
