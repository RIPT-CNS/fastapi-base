from pydantic import BaseModel
from typing import Optional, Literal


class BaseModelSchema(BaseModel):
    __abstract__ = True

    _id: int
    _created_at: float
    _updated_at: float


class PaginationParams(BaseModel):
    page_size: Optional[int] = 10
    page: Optional[int] = 1


class SortParams(BaseModel):
    sort_by: Optional[str] = "_id"
    order: Optional[Literal["asc", "desc"]] = "desc"
