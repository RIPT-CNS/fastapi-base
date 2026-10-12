from datetime import datetime
from enum import StrEnum
from typing import Any

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


class BulkResult(BaseModel):
    count: int = Field(description="Number of affected records")


class ImportMode(StrEnum):
    INSERT = "insert"  # every row is a new record
    UPDATE = "update"  # every row must match an existing record by the import key
    UPSERT = "upsert"  # update when the key matches, insert otherwise


class ImportRowError(BaseModel):
    row: int = Field(description="Excel row number (header = 1)")
    column: str | None = Field(None, description="Excel column letter")
    field: str | None = None
    message: str
    value: Any = None


class ImportResult(BaseModel):
    mode: ImportMode
    dry_run: bool = False
    total_rows: int = 0
    valid_rows: int = 0
    inserted: int = 0
    updated: int = 0
    ignored_columns: list[str] = []
    errors: list[ImportRowError] = []
