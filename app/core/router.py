import pkgutil
from importlib import import_module
from fastapi import APIRouter
from app.api import api_auth, api_healthcheck
from app.core.config import settings
import app.api as root_api

router = APIRouter()

router.include_router(api_healthcheck.router, tags=["[Current] Health Check"])
router.include_router(api_auth.router, tags=["[Current] Auth"])

for finder, subpackage_name, is_pkg in pkgutil.iter_modules(root_api.__path__):
    if is_pkg and subpackage_name.startswith("v"):
        subpackage = import_module(f"{root_api.__name__}.{subpackage_name}")
        for _, module_name, _ in pkgutil.iter_modules(subpackage.__path__):
            api_module = import_module(f"{subpackage.__name__}.{module_name}")
            version_router = getattr(api_module, "router", None)
            if version_router:
                if subpackage_name == settings.API_VERSION:
                    router.include_router(
                        version_router, tags=[f"[Current] {subpackage_name} - {module_name}"]
                    )
                router.include_router(
                    version_router,
                    tags=[f"{subpackage_name} - {module_name}"],
                    prefix=f"/{subpackage_name}",
                )
