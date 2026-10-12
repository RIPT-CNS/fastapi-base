import math
from typing import Any

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.schemas.sche_base import PaginationParams
from app.schemas.sche_response import MetadataResponse


def paginate(
    db: Session, stmt: Select, pagination_params: PaginationParams | None
) -> tuple[list[Any], MetadataResponse]:
    total = db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery())) or 0
    if pagination_params:
        page, page_size = pagination_params.page, pagination_params.page_size
        stmt = stmt.limit(page_size).offset((page - 1) * page_size)
    else:
        page, page_size = 1, total
    items = list(db.scalars(stmt).unique().all())
    metadata = MetadataResponse(
        page=page,
        page_size=page_size,
        total=total,
        total_pages=math.ceil(total / page_size) if page_size else 0,
    )
    return items, metadata
