from fastapi import APIRouter
from importlib import import_module

from app.api import router as general_router
from app.core.config import settings

router = APIRouter()

router.include_router(general_router)

for version in settings.API_VERSIONS.strip().split(","):
    try:
        api_module = import_module(f"app.api.{version}")
        version_router = getattr(api_module, "router", None)
        if version_router:
            if version == settings.API_VERSION:
                router.include_router(version_router)
            router.include_router(version_router, prefix=f"/{version}")
    except ModuleNotFoundError as e:
        print(f"API version '{version}' not found: {e}", flush=True)
