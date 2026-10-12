"""Test-only resources built like real modules: models + schemas + services + BaseAPI classes."""

from datetime import date
from typing import Any

from pydantic import Field
from sqlalchemy import ForeignKey, Integer, String, select
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.base_api import BaseAPI, BasePublicAPI, RouteConfig
from app.models import BareBaseModel, SoftDeleteMixin
from app.schemas.sche_base import BaseModelResponse, BaseSchema
from app.services.srv_base import BaseService, ImportContext, ImportRow


# ------------------------------------------------------------------ models
class Category(BareBaseModel):
    __tablename__ = "test_categories"

    name: Mapped[str] = mapped_column(String(50), unique=True)
    items: Mapped[list["Item"]] = relationship(back_populates="category")


class Item(SoftDeleteMixin, BareBaseModel):
    __tablename__ = "test_items"

    name: Mapped[str] = mapped_column(String(100))
    sku: Mapped[str | None] = mapped_column(String(30), unique=True)
    price: Mapped[int] = mapped_column(Integer, default=0)
    tags: Mapped[list[str]] = mapped_column(ARRAY(String(30)), default=list, server_default="{}")
    is_active: Mapped[bool] = mapped_column(default=True)
    released_on: Mapped[date | None]
    category_id: Mapped[int | None] = mapped_column(ForeignKey("test_categories.id"))
    category: Mapped[Category | None] = relationship(back_populates="items")


# ----------------------------------------------------------------- schemas
class CategorySchema(BaseSchema):
    name: str


class CategoryResponse(BaseModelResponse):
    name: str


class ItemCreate(BaseSchema):
    name: str = Field(min_length=2)
    sku: str | None = None
    price: int = Field(0, ge=0)
    tags: list[str] = []
    is_active: bool = True
    released_on: date | None = None
    category_id: int | None = None


class ItemUpdate(BaseSchema):
    name: str | None = Field(None, min_length=2)
    sku: str | None = None
    price: int | None = Field(None, ge=0)
    tags: list[str] | None = None
    is_active: bool | None = None
    released_on: date | None = None
    category_id: int | None = None


class ItemImport(BaseSchema):
    """Import columns differ from the API: category by name instead of id."""

    name: str = Field(min_length=2, title="Tên")
    sku: str | None = None
    price: int = Field(0, ge=0, description="Giá bán (VND)")
    tags: list[str] = []
    released_on: date | None = None
    category_name: str | None = None


class ItemResponse(BaseModelResponse):
    name: str
    sku: str | None
    price: int
    tags: list[str]
    is_active: bool
    released_on: date | None
    category_id: int | None


# ---------------------------------------------------------------- services
class CategoryService(BaseService[Category, CategorySchema, CategorySchema]):
    model = Category


class ItemService(BaseService[Item, ItemCreate, ItemUpdate]):
    model = Item
    search_fields = ("name", "sku")

    def import_validate_row(self, row: ImportRow, ctx: ImportContext) -> dict[str | None, str]:
        if "category_name" not in row.data:
            return {}
        name = row.data.pop("category_name")
        category = self.db.scalar(select(Category).where(Category.name == name)) if name else None
        if name and category is None:
            return {"category_name": f"Unknown category '{name}'"}
        row.data["category_id"] = category.id if category else None
        return {}

    def import_export_value(self, obj: Item, name: str) -> Any:
        if name == "category_name":
            return obj.category.name if obj.category else None
        return super().import_export_value(obj, name)


# -------------------------------------------------------------------- APIs
class ItemAPI(BaseAPI):
    prefix = "/test-items"
    service = ItemService
    response_schema = ItemResponse
    create_schema = ItemCreate
    update_schema = ItemUpdate
    import_schema = ItemImport
    route_config = {
        "read": RouteConfig(auth=False),
        "export": RouteConfig(auth=False),
        "delete": RouteConfig(roles=["admin"]),
    }


class AdminItemAPI(BaseAPI):
    """Model-level roles, no Excel."""

    prefix = "/test-admin-items"
    service = ItemService
    response_schema = ItemResponse
    create_schema = ItemCreate
    roles = ["admin"]
    enable_import = False
    enable_export = False


class CategoryAPI(BasePublicAPI):
    prefix = "/test-categories"
    service = CategoryService
    response_schema = CategoryResponse
    create_schema = CategorySchema
    update_schema = CategorySchema
    disabled_routes = ("delete_all", "import")


TEST_APIS = (ItemAPI, AdminItemAPI, CategoryAPI)
