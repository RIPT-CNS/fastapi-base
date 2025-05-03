from fastapi import APIRouter

from app.schemas.sche_base import BaseResponse

router = APIRouter()


@router.get("", response_model=BaseResponse)
async def get():
    return BaseResponse(http_code=200, message="OK")
