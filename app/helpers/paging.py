import logging
from pydantic import BaseModel
from abc import ABC, abstractmethod
from typing import Optional, Generic, Sequence, Type, TypeVar, Literal

from sqlalchemy import asc, desc
from sqlalchemy.orm import Query
from contextvars import ContextVar

from app.schemas.sche_base import BaseResponse, MetadataSchema
from app.helpers.exception_handler import CustomException

T = TypeVar("T")
C = TypeVar("C")

logger = logging.getLogger()


class PaginationParams(BaseModel):
    page_size: Optional[int] = 10
    page: Optional[int] = 1
    sort_by: Optional[str] = "id"
    order: Optional[Literal["asc", "desc"]] = "desc"


class BasePage(BaseResponse, BaseModel, Generic[T], ABC):
    data: Sequence[T]

    class Config:
        arbitrary_types_allowed = True

    @classmethod
    @abstractmethod
    def create(
        cls: Type[C],
        data: Sequence[T],
        metadata: MetadataSchema,
    ) -> C:
        pass  # pragma: no cover


class Page(BasePage[T], Generic[T]):
    metadata: MetadataSchema

    @classmethod
    def create(cls, data: Sequence[T], metadata: MetadataSchema) -> "Page[T]":
        return cls(data=data, metadata=metadata)


PageType: ContextVar[Type[BasePage]] = ContextVar("PageType", default=Page)


def paginate(model, query: Query, params: Optional[PaginationParams]) -> BasePage:
    try:
        total = query.count()

        if params.order:
            direction = desc if params.order == "desc" else asc
            query = query.order_by(direction(getattr(model, params.sort_by)))

        data = (
            query.limit(params.page_size)
            .offset(params.page_size * (params.page - 1))
            .all()
        )

        metadata = MetadataSchema(
            current_page=params.page, page_size=params.page_size, total=total
        )

    except Exception as e:
        raise CustomException(exception=e)

    return PageType.get().create(data, metadata)
