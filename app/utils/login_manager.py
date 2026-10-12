"""Authentication & authorization dependencies.

    @router.get("/me")
    def me(user: CurrentUser): ...

    @router.delete("/{id}", dependencies=[Depends(RoleRequired("admin"))])
    @router.post("", dependencies=[Depends(PermissionRequired("product:create"))])

Accepted credentials (each can be toggled in .env):
  - Authorization: Bearer <local JWT>       AUTH_LOCAL_ENABLED
  - Authorization: Bearer <Keycloak token>  KEYCLOAK_ENABLED
  - Authorization: Basic <user:pass>        AUTH_BASIC_ENABLED
"""

from typing import Annotated

from fastapi import Depends
from fastapi.security import (
    HTTPAuthorizationCredentials,
    HTTPBasic,
    HTTPBasicCredentials,
    HTTPBearer,
    OAuth2AuthorizationCodeBearer,
    OAuth2PasswordBearer,
)

from app.core.config import settings
from app.core.database import DbSession
from app.core.keycloak import keycloak_client
from app.models import User
from app.services.srv_auth import AuthService
from app.utils.exception_handler import CustomException, ExceptionType


async def _disabled_scheme() -> None:
    return None


# The schemes below only extract credentials (auto_error=False); they also make the
# matching "Authorize" options appear in Swagger UI.
_local_scheme = (
    OAuth2PasswordBearer(
        tokenUrl=f"{settings.API_PREFIX}/auth/token",
        scheme_name="LocalLogin",
        description="Username/password of a local account",
        auto_error=False,
    )
    if settings.AUTH_LOCAL_ENABLED
    else _disabled_scheme
)
_sso_scheme = (
    OAuth2AuthorizationCodeBearer(
        authorizationUrl=keycloak_client.authorization_endpoint,
        tokenUrl=keycloak_client.public_token_endpoint,
        refreshUrl=keycloak_client.public_token_endpoint,
        scopes={"openid": "OpenID", "profile": "Profile", "email": "Email"},
        scheme_name="KeycloakSSO",
        description="Login through Keycloak (authorization code + PKCE)",
        auto_error=False,
    )
    if keycloak_client is not None
    else _disabled_scheme
)
_bearer_scheme = HTTPBearer(
    scheme_name="BearerToken",
    description="Paste an access token (local JWT or Keycloak)",
    auto_error=False,
)
_basic_scheme = (
    HTTPBasic(scheme_name="BasicAuth", auto_error=False)
    if settings.AUTH_BASIC_ENABLED
    else _disabled_scheme
)


def get_current_user_optional(
    db: DbSession,
    local_token: Annotated[str | None, Depends(_local_scheme)],
    sso_token: Annotated[str | None, Depends(_sso_scheme)],
    bearer: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)],
    basic: Annotated[HTTPBasicCredentials | None, Depends(_basic_scheme)],
) -> User | None:
    """The authenticated user, or None when no credentials were sent.
    Invalid credentials always raise 401."""
    token = local_token or sso_token or (bearer.credentials if bearer else None)
    if token:
        return AuthService(db).authenticate_token(token)
    if basic:
        return AuthService(db).authenticate_basic(basic.username, basic.password)
    return None


def get_current_user(
    user: Annotated[User | None, Depends(get_current_user_optional)],
) -> User:
    if user is None:
        raise CustomException(
            ExceptionType.UNAUTHORIZED,
            "Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
OptionalUser = Annotated[User | None, Depends(get_current_user_optional)]


class AuthenticateRequired:
    """Kept for compatibility: Depends(AuthenticateRequired()) == Depends(get_current_user)."""

    def __call__(self, user: CurrentUser) -> User:
        return user


class RoleRequired:
    """User must have at least one of the roles (local or from the SSO token)."""

    def __init__(self, *roles: str):
        self.roles = frozenset(roles)

    def __call__(self, user: CurrentUser) -> User:
        if self.roles and not user.has_role(*self.roles):
            raise CustomException(ExceptionType.FORBIDDEN)
        return user


class PermissionRequired:
    """User must have every permission, resolved from roles by app.core.permissions."""

    def __init__(self, *permissions: str):
        self.permissions = permissions

    def __call__(self, user: CurrentUser) -> User:
        if not all(user.has_permission(permission) for permission in self.permissions):
            raise CustomException(ExceptionType.FORBIDDEN)
        return user
