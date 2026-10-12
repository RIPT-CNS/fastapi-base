from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Integer, String
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from app.core.permissions import has_permission
from app.models.model_base import BareBaseModel
from app.utils.enums import AuthProvider


class User(BareBaseModel):
    __tablename__ = "users"

    username: Mapped[str] = mapped_column(String(150), unique=True, index=True)
    email: Mapped[str | None] = mapped_column(String(255), unique=True, index=True)
    # Null for SSO-only accounts
    hashed_password: Mapped[str | None] = mapped_column(String(255))
    auth_provider: Mapped[str] = mapped_column(
        String(20), default=AuthProvider.LOCAL, server_default=AuthProvider.LOCAL
    )
    # Subject ("sub" claim) of the linked Keycloak account
    sso_sub: Mapped[str | None] = mapped_column(String(255), unique=True, index=True)

    full_name: Mapped[str | None] = mapped_column(String(255), index=True)
    first_name: Mapped[str | None] = mapped_column(String(100))
    last_name: Mapped[str | None] = mapped_column(String(100))
    dob: Mapped[date | None] = mapped_column(Date)
    gender: Mapped[str | None] = mapped_column(String(20))
    phone: Mapped[str | None] = mapped_column(String(30), index=True)
    address: Mapped[str | None] = mapped_column(String(500))
    identity_card: Mapped[str | None] = mapped_column(String(50), index=True)
    identity_card_date: Mapped[date | None] = mapped_column(Date)
    identity_card_place: Mapped[str | None] = mapped_column(String(255))

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    roles: Mapped[list[str]] = mapped_column(
        ARRAY(String(50)), default=list, server_default="{}", nullable=False
    )
    last_login: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Bumped on logout / password change: every local JWT issued before is rejected
    token_version: Mapped[int] = mapped_column(Integer, default=0, server_default="0")

    # Roles granted by the identity provider (Keycloak) for the current request; not persisted
    _token_roles = frozenset()

    @property
    def all_roles(self) -> frozenset[str]:
        """Local roles + roles from the SSO access token."""
        return frozenset(self.roles or ()) | self._token_roles

    def set_token_roles(self, roles: set[str] | frozenset[str]) -> None:
        self._token_roles = frozenset(roles)

    def has_role(self, *roles: str) -> bool:
        return bool(self.all_roles & set(roles))

    def has_permission(self, permission: str) -> bool:
        return has_permission(self.all_roles, permission)
