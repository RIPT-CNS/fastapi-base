from typing import Any

from fastapi import APIRouter
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.core.database import DbSession
from app.schemas.sche_response import BaseResponse
from app.utils.exception_handler import CustomException, ExceptionType

router = APIRouter(prefix="/health-check")


@router.get("", response_model=BaseResponse)
async def liveness() -> Any:
    return BaseResponse(message="OK")


@router.get("/ready", response_model=BaseResponse)
def readiness(db: DbSession) -> Any:
    """Checks the database connection."""
    try:
        db.execute(text("SELECT 1"))
    except SQLAlchemyError as e:
        raise CustomException(ExceptionType.SERVICE_UNAVAILABLE, "Database unavailable") from e
    return BaseResponse(message="OK")
