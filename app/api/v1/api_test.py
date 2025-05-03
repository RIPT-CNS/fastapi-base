from typing import Any

from fastapi import APIRouter

from app.helpers.exception_handler import CustomException


router = APIRouter()


@router.get("/hello-world", response_model=str)
def get() -> Any:
    try:
        return "Hello World v1"
    except Exception as e:
        return CustomException(exception=e)
