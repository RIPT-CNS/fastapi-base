from fastapi import APIRouter
from app.api import api_auth, api_healthcheck

router = APIRouter()

router.include_router(
    api_healthcheck.router, tags=["health-check"], prefix=f"/health-check"
)
router.include_router(api_auth.router, tags=["auth"], prefix=f"/auth")
