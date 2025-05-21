from typing import Any

from fastapi import APIRouter

from app.utils.exception_handler import CustomException


router = APIRouter(prefix=f"/test")


@router.get("/hello-world", response_model=str)
def get() -> Any:
    try:
        return "Hello World v2"
    except Exception as e:
        return CustomException(exception=e)
