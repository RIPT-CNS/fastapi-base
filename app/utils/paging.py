from typing import Optional, List, Any
from sqlalchemy import asc, desc
from sqlalchemy.orm import Query
from app.schemas.sche_response import MetadataResponse
from app.utils.exception_handler import CustomException
from app.schemas.sche_base import PaginationParams, SortParams


def paginate(
    model,
    query: Query,
    pagination_params: Optional[PaginationParams],
    sort_params: Optional[SortParams],
) -> List[Any]:
    try:
        total = query.count()
        metadata = MetadataResponse(
            page=1,
            page_size=total,
            total=total,
        )
        if sort_params and sort_params.order:
            direction = desc if sort_params.order == "desc" else asc
            query = query.order_by(direction(getattr(model, sort_params.sort_by)))
        if pagination_params:
            if pagination_params.page_size:
                query = query.limit(pagination_params.page_size)
            if pagination_params.page:
                query = query.offset(
                    pagination_params.page_size * (pagination_params.page - 1)
                )
            metadata = MetadataResponse(
                page=pagination_params.page,
                page_size=pagination_params.page_size,
                total=total,
            )
        data = query.all()
        print("============ PAGINATE ============", data, metadata, flush=True)
    except Exception as e:
        raise CustomException(exception=e)
    return data, metadata
