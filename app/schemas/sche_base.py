from pydantic import BaseModel
from typing import Optional, Literal


class BaseModelResponse(BaseModel):
    id: int
    created_at: float
    updated_at: float


class PaginationParams(BaseModel):
    page_size: Optional[int] = 10
    page: Optional[int] = 1


class SortParams(BaseModel):
    sort_by: Optional[str] = "id"
    order: Optional[Literal["asc", "desc"]] = "desc"
