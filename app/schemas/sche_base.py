from datetime import datetime
from typing import Any, ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.core.config import settings


class BaseSchema(BaseModel):
    """Base for request/response schemas. Can be built directly from ORM objects."""

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class BaseModelResponse(BaseSchema):
    id: int
    created_at: datetime
    updated_at: datetime


class PaginationParams(BaseModel):
    page: int = Field(1, ge=1)
    page_size: int = Field(settings.PAGE_SIZE_DEFAULT, ge=1, le=settings.PAGE_SIZE_MAX)


class SortParams(BaseModel):
    sort_by: str | None = None
    order: Literal["asc", "desc"] = "desc"


class ListQueryParams(BaseModel):
    """Base of the query-string model generated per resource by CRUDRouter.

    Generated subclasses add `sort_by` (enum of sortable fields), `search`
    and one field per declared filter, e.g. `price__gte`.
    """

    RESERVED: ClassVar[frozenset[str]] = frozenset(
        {"page", "page_size", "sort_by", "order", "search"}
    )

    page: int = Field(1, ge=1)
    page_size: int = Field(settings.PAGE_SIZE_DEFAULT, ge=1, le=settings.PAGE_SIZE_MAX)

    def pagination(self) -> PaginationParams:
        return PaginationParams(page=self.page, page_size=self.page_size)

    def sorting(self) -> SortParams:
        return SortParams(
            sort_by=getattr(self, "sort_by", None), order=getattr(self, "order", "desc")
        )

    def filters(self) -> dict[str, Any]:
        values = self.model_dump(exclude=set(self.RESERVED))
        return {key: value for key, value in values.items() if value is not None}
