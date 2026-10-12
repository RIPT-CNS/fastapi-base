"""Test-only resource built like a real module: model + schemas + service + router."""

from sqlalchemy import Integer, String
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from app.core.crud_router import CRUDRouter
from app.models import BareBaseModel, SoftDeleteMixin
from app.schemas.sche_base import BaseModelResponse, BaseSchema
from app.services.srv_base import BaseService


class Item(SoftDeleteMixin, BareBaseModel):
    __tablename__ = "test_items"

    name: Mapped[str] = mapped_column(String(100))
    price: Mapped[int] = mapped_column(Integer, default=0)
    category: Mapped[str | None] = mapped_column(String(50))
    tags: Mapped[list[str]] = mapped_column(ARRAY(String(30)), default=list, server_default="{}")
    is_active: Mapped[bool] = mapped_column(default=True)


class ItemCreate(BaseSchema):
    name: str
    price: int = 0
    category: str | None = None
    tags: list[str] = []
    is_active: bool = True


class ItemUpdate(BaseSchema):
    name: str | None = None
    price: int | None = None
    category: str | None = None
    tags: list[str] | None = None
    is_active: bool | None = None


class ItemResponse(BaseModelResponse):
    name: str
    price: int
    category: str | None
    tags: list[str]
    is_active: bool


class ItemService(BaseService[Item, ItemCreate, ItemUpdate]):
    model = Item
    search_fields = ("name", "category")
    filter_fields = {
        "price": ("gte", "lte"),
        "category": ("eq", "in", "isnull"),
        "tags": ("eq",),
        "is_active": ("eq",),
        "name": ("like",),
    }
    sort_fields = ("id", "name", "price")


items_router = CRUDRouter(
    prefix="/test-items",
    service=ItemService,
    response_schema=ItemResponse,
    create_schema=ItemCreate,
    update_schema=ItemUpdate,
    permissions={"list": None, "get": None, "delete": ["admin"]},
)
