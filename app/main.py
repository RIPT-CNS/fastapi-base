import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from app.core.config import settings
from app.core.logging import setup_logging

setup_logging()

from app.core.database import engine  # noqa: E402
from app.core.middleware import RequestContextMiddleware  # noqa: E402
from app.core.router import router  # noqa: E402
from app.utils.exception_handler import register_exception_handlers  # noqa: E402

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    logger.info(
        "Starting %s v%s (env=%s, keycloak=%s, basic_auth=%s)",
        settings.PROJECT_NAME,
        settings.VERSION,
        settings.ENVIRONMENT,
        settings.KEYCLOAK_ENABLED,
        settings.AUTH_BASIC_ENABLED,
    )
    yield
    engine.dispose()


def get_application() -> FastAPI:
    swagger_oauth = None
    if settings.KEYCLOAK_ENABLED:
        swagger_oauth = {
            "clientId": settings.KEYCLOAK_FRONTEND_CLIENT_ID or settings.KEYCLOAK_CLIENT_ID,
            "usePkceWithAuthorizationCodeGrant": True,
            "scopes": "openid profile email",
        }

    application = FastAPI(
        title=settings.PROJECT_NAME,
        version=settings.VERSION,
        description=(
            "FastAPI + PostgreSQL base: local JWT, HTTP Basic, Keycloak SSO, RBAC and generic CRUD."
        ),
        debug=settings.DEBUG,
        lifespan=lifespan,
        docs_url="/docs" if settings.DOCS_ENABLED else None,
        redoc_url="/re-docs" if settings.DOCS_ENABLED else None,
        openapi_url=f"{settings.API_PREFIX}/openapi.json" if settings.DOCS_ENABLED else None,
        swagger_ui_init_oauth=swagger_oauth,
        swagger_ui_parameters={
            "docExpansion": "none",
            "persistAuthorization": True,
            "displayRequestDuration": True,
        },
    )

    # Last added = outermost
    application.add_middleware(GZipMiddleware, minimum_size=1024)
    if settings.BACKEND_CORS_ORIGINS:
        application.add_middleware(
            CORSMiddleware,
            allow_origins=settings.BACKEND_CORS_ORIGINS,
            allow_credentials="*" not in settings.BACKEND_CORS_ORIGINS,
            allow_methods=["*"],
            allow_headers=["*"],
            expose_headers=["X-Request-ID"],
        )
    application.add_middleware(RequestContextMiddleware)

    application.include_router(router, prefix=settings.API_PREFIX)
    register_exception_handlers(application)
    return application


app = get_application()
