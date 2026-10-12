"""Keycloak (OpenID Connect) client.

Access tokens are verified locally with the realm public keys (JWKS, cached),
so authenticating a request does not call Keycloak.
"""

import logging
import ssl
from typing import Any
from urllib.parse import urlencode

import httpx
import jwt

from app.core.config import Settings, settings
from app.utils.exception_handler import CustomException, ExceptionType

logger = logging.getLogger(__name__)

_ALGORITHMS = ["RS256", "RS384", "RS512", "PS256", "PS384", "PS512", "ES256", "ES384", "ES512"]


class KeycloakClient:
    def __init__(self, config: Settings):
        self.realm = config.KEYCLOAK_REALM
        self.client_id = config.KEYCLOAK_CLIENT_ID
        self.client_secret = config.KEYCLOAK_CLIENT_SECRET
        self.frontend_client_id = config.KEYCLOAK_FRONTEND_CLIENT_ID or config.KEYCLOAK_CLIENT_ID
        self.audience = config.KEYCLOAK_AUDIENCE or config.KEYCLOAK_CLIENT_ID

        server_url = config.KEYCLOAK_SERVER_URL.rstrip("/")
        public_url = (config.KEYCLOAK_PUBLIC_URL or server_url).rstrip("/")
        self.issuer = f"{public_url}/realms/{self.realm}"
        self._public_oidc = f"{self.issuer}/protocol/openid-connect"
        self._internal_oidc = f"{server_url}/realms/{self.realm}/protocol/openid-connect"

        self._http = httpx.Client(
            timeout=config.KEYCLOAK_TIMEOUT, verify=config.KEYCLOAK_VERIFY_SSL
        )
        ssl_context = None if config.KEYCLOAK_VERIFY_SSL else ssl._create_unverified_context()
        self._jwks = jwt.PyJWKClient(
            f"{self._internal_oidc}/certs",
            cache_jwk_set=True,
            lifespan=300,
            timeout=int(config.KEYCLOAK_TIMEOUT),
            ssl_context=ssl_context,
        )

    # ------------------------------------------------- browser-facing endpoints
    @property
    def authorization_endpoint(self) -> str:
        return f"{self._public_oidc}/auth"

    @property
    def public_token_endpoint(self) -> str:
        return f"{self._public_oidc}/token"

    @property
    def end_session_endpoint(self) -> str:
        return f"{self._public_oidc}/logout"

    def authorization_url(
        self,
        redirect_uri: str,
        state: str,
        code_challenge: str | None = None,
        scope: str = "openid profile email",
    ) -> str:
        params = {
            "client_id": self.client_id,
            "response_type": "code",
            "redirect_uri": redirect_uri,
            "scope": scope,
            "state": state,
        }
        if code_challenge:
            params |= {"code_challenge": code_challenge, "code_challenge_method": "S256"}
        return f"{self.authorization_endpoint}?{urlencode(params)}"

    # ----------------------------------------------------------- verification
    def verify_token(self, token: str) -> dict[str, Any]:
        try:
            signing_key = self._jwks.get_signing_key_from_jwt(token)
            claims = jwt.decode(
                token,
                signing_key.key,
                algorithms=_ALGORITHMS,
                issuer=self.issuer,
                audience=self.audience,
                options={"require": ["exp", "iat", "sub"]},
                leeway=10,
            )
        except jwt.PyJWKClientConnectionError as e:
            logger.error("Cannot fetch Keycloak JWKS: %s", e)
            raise CustomException(
                ExceptionType.SERVICE_UNAVAILABLE, "SSO provider unavailable"
            ) from e
        except jwt.ExpiredSignatureError as e:
            raise CustomException(ExceptionType.UNAUTHORIZED, "Token expired") from e
        except jwt.PyJWTError as e:
            raise CustomException(ExceptionType.UNAUTHORIZED, "Invalid token") from e
        # Reject ID / refresh tokens used as access tokens
        if claims.get("typ", "Bearer") != "Bearer":
            raise CustomException(ExceptionType.UNAUTHORIZED, "Invalid token type")
        return claims

    def extract_roles(self, claims: dict[str, Any]) -> set[str]:
        """Realm roles + client roles of the backend and frontend clients."""
        roles = set(claims.get("realm_access", {}).get("roles", []))
        resource_access = claims.get("resource_access", {})
        for client_id in {self.client_id, self.frontend_client_id}:
            roles |= set(resource_access.get(client_id, {}).get("roles", []))
        return roles

    # ------------------------------------------------------- token endpoint
    def _client_credentials(self) -> dict[str, str]:
        credentials = {"client_id": self.client_id}
        if self.client_secret:
            credentials["client_secret"] = self.client_secret
        return credentials

    def _post(self, path: str, data: dict[str, str]) -> dict[str, Any]:
        try:
            response = self._http.post(
                f"{self._internal_oidc}/{path}", data=data | self._client_credentials()
            )
        except httpx.HTTPError as e:
            logger.error("Keycloak request failed: %s", e)
            raise CustomException(
                ExceptionType.SERVICE_UNAVAILABLE, "SSO provider unavailable"
            ) from e
        if response.status_code in (400, 401):
            try:
                error = response.json()
            except ValueError:
                error = {}
            message = error.get("error_description") or error.get("error") or "SSO error"
            raise CustomException(ExceptionType.UNAUTHORIZED, message)
        if response.status_code >= 300:
            logger.error("Keycloak %s -> %s: %s", path, response.status_code, response.text)
            raise CustomException(ExceptionType.SERVICE_UNAVAILABLE, "SSO provider error")
        return response.json() if response.content else {}

    def password_grant(self, username: str, password: str) -> dict[str, Any]:
        """Resource Owner Password grant. Requires "Direct access grants" on the client."""
        return self._post(
            "token",
            {
                "grant_type": "password",
                "username": username,
                "password": password,
                "scope": "openid",
            },
        )

    def exchange_code(
        self, code: str, redirect_uri: str, code_verifier: str | None = None
    ) -> dict[str, Any]:
        data = {"grant_type": "authorization_code", "code": code, "redirect_uri": redirect_uri}
        if code_verifier:
            data["code_verifier"] = code_verifier
        return self._post("token", data)

    def refresh(self, refresh_token: str) -> dict[str, Any]:
        return self._post("token", {"grant_type": "refresh_token", "refresh_token": refresh_token})

    def logout(self, refresh_token: str) -> None:
        self._post("logout", {"refresh_token": refresh_token})


keycloak_client: KeycloakClient | None = (
    KeycloakClient(settings) if settings.KEYCLOAK_ENABLED else None
)
