"""Keycloak SSO endpoints (mounted only when KEYCLOAK_ENABLED=true).

Typical flows:
  * SPA with its own OIDC library (keycloak-js, oidc-client-ts): read GET /auth/sso/config,
    log in on Keycloak, send the access token as "Authorization: Bearer". Nothing else needed.
  * Backend-driven login: open GET /auth/sso/authorize in the browser -> Keycloak login page
    -> GET /auth/sso/callback returns the tokens.
  * Frontend receives ?code= itself: POST /auth/sso/token {code, redirect_uri}.
"""

import base64
import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

import jwt
from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse

from app.core.config import settings
from app.core.keycloak import keycloak_client
from app.schemas.sche_auth import (
    LoginRequest,
    RefreshTokenRequest,
    SSOCodeRequest,
    SSOConfigResponse,
    TokenResponse,
)
from app.schemas.sche_response import BaseResponse, DataResponse
from app.services.srv_auth import AuthService
from app.utils.exception_handler import CustomException, ExceptionType

router = APIRouter(prefix="/auth/sso")

AuthServiceDep = Annotated[AuthService, Depends()]

_STATE_COOKIE = "sso_state"
_STATE_TTL = timedelta(minutes=10)


@router.get("/config", response_model=DataResponse[SSOConfigResponse])
def sso_config() -> Any:
    """Public OIDC settings for frontends."""
    return DataResponse(
        data=SSOConfigResponse(
            issuer=keycloak_client.issuer,
            realm=keycloak_client.realm,
            client_id=keycloak_client.frontend_client_id,
            authorization_endpoint=keycloak_client.authorization_endpoint,
            token_endpoint=keycloak_client.public_token_endpoint,
            end_session_endpoint=keycloak_client.end_session_endpoint,
        )
    )


@router.post("/login", response_model=DataResponse[TokenResponse])
def sso_login(payload: LoginRequest, auth_service: AuthServiceDep) -> Any:
    """Username/password login against Keycloak (Direct Access Grant)."""
    return DataResponse(data=auth_service.sso_login(payload.username, payload.password))


@router.get("/authorize", response_class=RedirectResponse, status_code=307)
def sso_authorize(request: Request) -> RedirectResponse:
    """Redirect the browser to the Keycloak login page (authorization code + PKCE)."""
    state = secrets.token_urlsafe(24)
    code_verifier = secrets.token_urlsafe(48)
    code_challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(code_verifier.encode()).digest())
        .rstrip(b"=")
        .decode()
    )
    redirect_uri = str(request.url_for("sso_callback"))
    response = RedirectResponse(
        keycloak_client.authorization_url(redirect_uri, state, code_challenge), status_code=307
    )
    cookie = jwt.encode(
        {"state": state, "verifier": code_verifier, "exp": datetime.now(UTC) + _STATE_TTL},
        settings.SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )
    response.set_cookie(
        _STATE_COOKIE,
        cookie,
        max_age=int(_STATE_TTL.total_seconds()),
        httponly=True,
        samesite="lax",
        secure=request.url.scheme == "https",
        path=f"{settings.API_PREFIX}/auth/sso",
    )
    return response


@router.get("/callback", name="sso_callback", response_model=DataResponse[TokenResponse])
def sso_callback(request: Request, code: str, state: str, auth_service: AuthServiceDep) -> Any:
    try:
        saved = jwt.decode(
            request.cookies.get(_STATE_COOKIE, ""),
            settings.SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
    except jwt.PyJWTError as e:
        raise CustomException(ExceptionType.BAD_REQUEST, "Login session expired") from e
    if not secrets.compare_digest(saved.get("state", ""), state):
        raise CustomException(ExceptionType.BAD_REQUEST, "Invalid state")
    tokens = auth_service.sso_exchange_code(
        code, str(request.url_for("sso_callback")), saved.get("verifier")
    )
    return DataResponse(data=tokens)


@router.post("/token", response_model=DataResponse[TokenResponse])
def sso_token(payload: SSOCodeRequest, auth_service: AuthServiceDep) -> Any:
    """Exchange an authorization code received by the frontend."""
    tokens = auth_service.sso_exchange_code(
        payload.code, payload.redirect_uri, payload.code_verifier
    )
    return DataResponse(data=tokens)


@router.post("/refresh", response_model=DataResponse[TokenResponse])
def sso_refresh(payload: RefreshTokenRequest, auth_service: AuthServiceDep) -> Any:
    return DataResponse(data=auth_service.sso_refresh(payload.refresh_token))


@router.post("/logout", response_model=BaseResponse)
def sso_logout(payload: RefreshTokenRequest, auth_service: AuthServiceDep) -> Any:
    """End the Keycloak session of this refresh token."""
    auth_service.sso_logout(payload.refresh_token)
    return BaseResponse(message="Logged out")
