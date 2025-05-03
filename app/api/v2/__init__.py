from fastapi import APIRouter
from app.api.v2 import api_test

router = APIRouter()

router.include_router(api_test.router, tags=["test"], prefix=f"/test")
