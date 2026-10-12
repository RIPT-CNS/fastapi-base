from datetime import UTC, datetime
from typing import Any

from app.core.config import settings
from app.core.database import DbSession
from app.core.keycloak import KeycloakClient, keycloak_client
from app.core.security import TokenType, create_token, decode_token, get_unverified_issuer
from app.models import User
from app.schemas.sche_auth import RegisterRequest, TokenResponse
from app.services.srv_user import UserService
from app.utils.exception_handler import CustomException, ExceptionType


class AuthService:
    def __init__(self, db: DbSession) -> None:
        self.db = db
        self.user_service = UserService(db)

    # ============================================================ local JWT
    def _ensure_local_enabled(self) -> None:
        if not settings.AUTH_LOCAL_ENABLED:
            raise CustomException(ExceptionType.FORBIDDEN, "Local login is disabled")

    def create_tokens(self, user: User) -> TokenResponse:
        access_token, expires_in = create_token(
            str(user.id), TokenType.ACCESS, version=user.token_version
        )
        refresh_token, refresh_expires_in = create_token(
            str(user.id), TokenType.REFRESH, version=user.token_version
        )
        return TokenResponse(
            access_token=access_token,
            expires_in=expires_in,
            refresh_token=refresh_token,
            refresh_expires_in=refresh_expires_in,
        )

    def login(self, username: str, password: str) -> TokenResponse:
        self._ensure_local_enabled()
        user = self.user_service.authenticate(username, password)
        self._touch_last_login(user)
        return self.create_tokens(user)

    def refresh(self, refresh_token: str) -> TokenResponse:
        self._ensure_local_enabled()
        user = self._get_local_user(decode_token(refresh_token, TokenType.REFRESH))
        return self.create_tokens(user)

    def register(self, data: RegisterRequest) -> User:
        self._ensure_local_enabled()
        if not settings.AUTH_REGISTRATION_ENABLED:
            raise CustomException(ExceptionType.FORBIDDEN, "Registration is disabled")
        values = data.model_dump() | {"roles": list(settings.DEFAULT_USER_ROLES), "is_active": True}
        return self.user_service.create(values)

    def logout(self, user: User) -> None:
        """Revoke every local token of the user (all devices)."""
        user.token_version += 1
        self.db.commit()

    def change_password(
        self, user: User, current_password: str, new_password: str
    ) -> TokenResponse:
        self._ensure_local_enabled()
        if not user.hashed_password:
            raise CustomException(
                ExceptionType.BAD_REQUEST, "SSO account: change the password on the SSO provider"
            )
        self.user_service.authenticate(user.username, current_password)
        self.user_service.set_password(user, new_password)
        return self.create_tokens(user)

    def _get_local_user(self, payload: dict[str, Any]) -> User:
        try:
            user_id = int(payload["sub"])
        except (KeyError, ValueError) as e:
            raise CustomException(ExceptionType.UNAUTHORIZED, "Invalid token") from e
        user = self.user_service.get_by_id_optional(user_id)
        if user is None or payload.get("ver", 0) != user.token_version:
            raise CustomException(ExceptionType.UNAUTHORIZED, "Token revoked")
        self._ensure_active(user)
        return user

    # ====================================================== request auth
    def authenticate_token(self, token: str) -> User:
        """Bearer token -> user. Local JWT or Keycloak access token, chosen by the `iss` claim."""
        issuer = get_unverified_issuer(token)
        if settings.AUTH_LOCAL_ENABLED and issuer == settings.jwt_issuer:
            return self._get_local_user(decode_token(token, TokenType.ACCESS))
        if keycloak_client is not None and issuer == keycloak_client.issuer:
            return self._get_sso_user(keycloak_client.verify_token(token))
        raise CustomException(ExceptionType.UNAUTHORIZED, "Invalid token")

    def authenticate_basic(self, username: str, password: str) -> User:
        return self.user_service.authenticate(username, password)

    def _get_sso_user(self, claims: dict[str, Any]) -> User:
        user = self.user_service.sync_sso_user(claims)
        self._ensure_active(user)
        user.set_token_roles(self._keycloak.extract_roles(claims))
        return user

    @staticmethod
    def _ensure_active(user: User) -> None:
        if not user.is_active:
            raise CustomException(ExceptionType.FORBIDDEN, "User is inactive")

    def _touch_last_login(self, user: User) -> None:
        user.last_login = datetime.now(UTC)
        self.db.commit()

    # ======================================================= Keycloak SSO
    @property
    def _keycloak(self) -> KeycloakClient:
        if keycloak_client is None:
            raise CustomException(ExceptionType.NOT_FOUND, "SSO is not enabled")
        return keycloak_client

    def _sso_tokens(self, tokens: dict[str, Any]) -> TokenResponse:
        user = self._get_sso_user(self._keycloak.verify_token(tokens["access_token"]))
        self._touch_last_login(user)
        return TokenResponse(**tokens)

    def sso_login(self, username: str, password: str) -> TokenResponse:
        return self._sso_tokens(self._keycloak.password_grant(username, password))

    def sso_exchange_code(
        self, code: str, redirect_uri: str, code_verifier: str | None = None
    ) -> TokenResponse:
        return self._sso_tokens(self._keycloak.exchange_code(code, redirect_uri, code_verifier))

    def sso_refresh(self, refresh_token: str) -> TokenResponse:
        return TokenResponse(**self._keycloak.refresh(refresh_token))

    def sso_logout(self, refresh_token: str) -> None:
        self._keycloak.logout(refresh_token)
