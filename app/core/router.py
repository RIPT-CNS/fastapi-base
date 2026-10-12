"""Router auto-discovery.

Every `api_*.py` module inside a version package (app/api/v1, app/api/v2, ...) that defines
`router` is mounted at {API_PREFIX}/{version}. The version named by API_VERSION is also
mounted without version prefix ({API_PREFIX}/users == {API_PREFIX}/v1/users), hidden from docs.
"""

import pkgutil
from importlib import import_module

from fastapi import APIRouter

import app.api as root_api
from app.api import api_auth, api_healthcheck
from app.core.config import settings

router = APIRouter()

router.include_router(api_healthcheck.router, tags=["Health Check"])
router.include_router(api_auth.router, tags=["Auth"])
if settings.KEYCLOAK_ENABLED:
    from app.api import api_auth_sso

    router.include_router(api_auth_sso.router, tags=["Auth - SSO (Keycloak)"])

for _, version, is_pkg in pkgutil.iter_modules(root_api.__path__):
    if not (is_pkg and version.startswith("v")):
        continue
    package = import_module(f"{root_api.__name__}.{version}")
    for _, module_name, _ in pkgutil.iter_modules(package.__path__):
        if not module_name.startswith("api_"):
            continue
        module_router = getattr(import_module(f"{package.__name__}.{module_name}"), "router", None)
        if module_router is None:
            continue
        router.include_router(module_router, prefix=f"/{version}")
        if version == settings.API_VERSION:
            router.include_router(module_router, include_in_schema=False)
