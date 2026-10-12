from typing import Any, Generic, TypeVar

from pydantic import BaseModel, model_validator

T = TypeVar("T")


class MetadataResponse(BaseModel):
    page: int
    page_size: int
    total: int
    total_pages: int


class BaseResponse(BaseModel):
    """Envelope shared by every response: {http_code, success, message, ...}."""

    http_code: int = 200
    success: bool = True
    message: str | None = None

    @model_validator(mode="after")
    def _compute_success(self) -> "BaseResponse":
        self.success = self.http_code < 400
        return self


class DataResponse(BaseResponse, Generic[T]):
    data: T | None = None


class PageResponse(BaseResponse, Generic[T]):
    data: list[T] = []
    metadata: MetadataResponse


class ErrorResponse(BaseResponse):
    errors: list[dict[str, Any]] | None = None
