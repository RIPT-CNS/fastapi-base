from fastapi import APIRouter

from app.schemas.sche_response import BaseResponse

router = APIRouter(prefix=f"/health-check")


@router.get("", response_model=BaseResponse)
async def get():
    return BaseResponse(http_code=200, message="OK")
