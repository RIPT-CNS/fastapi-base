from fastapi import APIRouter
from app.api.v1 import api_test, api_user

router = APIRouter()

router.include_router(api_test.router, tags=["test"], prefix=f"/test")
router.include_router(api_user.router, tags=["users"], prefix=f"/users")
