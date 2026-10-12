from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.schemas.sche_user import USERNAME_PATTERN, UserProfile


class LoginRequest(BaseModel):
    username: str = Field(description="Username or email")
    password: str


class RegisterRequest(UserProfile):
    username: str = Field(min_length=3, max_length=150, pattern=USERNAME_PATTERN)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class RefreshTokenRequest(BaseModel):
    refresh_token: str


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8, max_length=128)


class TokenResponse(BaseModel):
    """Same shape for local JWT and Keycloak tokens, so clients handle both identically."""

    model_config = ConfigDict(extra="ignore")

    access_token: str
    token_type: str = "Bearer"
    expires_in: int | None = None
    refresh_token: str | None = None
    refresh_expires_in: int | None = None
    id_token: str | None = None
    scope: str | None = None


class SSOCodeRequest(BaseModel):
    code: str
    redirect_uri: str
    code_verifier: str | None = None


class SSOConfigResponse(BaseModel):
    issuer: str
    realm: str
    client_id: str = Field(description="Public client id for frontends (PKCE)")
    authorization_endpoint: str
    token_endpoint: str
    end_session_endpoint: str
