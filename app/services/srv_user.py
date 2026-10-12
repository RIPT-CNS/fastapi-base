import re
import secrets
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError

from app.core.config import settings
from app.core.security import get_password_hash, verify_password
from app.models import User
from app.schemas.sche_user import UserCreateRequest, UserUpdateRequest
from app.services.srv_base import BaseService, ImportContext
from app.utils.enums import AuthProvider, UserRole
from app.utils.exception_handler import CustomException, ExceptionType


class UserService(BaseService[User, UserCreateRequest, UserUpdateRequest]):
    model = User
    search_fields = ("username", "email", "full_name", "phone")

    def get_by_login(self, login: str) -> User | None:
        """Find by username or email."""
        login = login.strip()
        return self.db.scalar(
            self.get_query()
            .where(or_(User.username == login, User.email == login.lower()))
            .limit(1)
        )

    def authenticate(self, login: str, password: str) -> User:
        user = self.get_by_login(login)
        if not verify_password(password, user.hashed_password if user else None):
            raise CustomException(ExceptionType.UNAUTHORIZED, "Incorrect username or password")
        if not user.is_active:
            raise CustomException(ExceptionType.FORBIDDEN, "User is inactive")
        return user

    def set_password(self, user: User, password: str) -> None:
        """Change password and revoke every token issued before."""
        user.hashed_password = get_password_hash(password)
        user.token_version += 1
        self._save(user, commit=True)

    # ------------------------------------------------------------------ hooks
    def import_transform_row(self, values: dict[str, Any], ctx: ImportContext) -> dict[str, Any]:
        values = super().import_transform_row(values, ctx)
        if isinstance(values.get("email"), str):
            values["email"] = values["email"].lower()  # compared lower-case by the unique check
        return values

    def before_create(self, data: dict[str, Any]) -> dict[str, Any]:
        password = data.pop("password", None)
        if password:
            data["hashed_password"] = get_password_hash(password)
        if data.get("email"):
            data["email"] = data["email"].lower()
        self._ensure_unique(username=data.get("username"), email=data.get("email"))
        return data

    def before_update(self, user: User, data: dict[str, Any]) -> dict[str, Any]:
        password = data.pop("password", None)
        if password:
            data["hashed_password"] = get_password_hash(password)
            data["token_version"] = user.token_version + 1
        if data.get("email"):
            data["email"] = data["email"].lower()
            self._ensure_unique(email=data["email"], exclude_id=user.id)
        return data

    def _ensure_unique(
        self,
        *,
        username: str | None = None,
        email: str | None = None,
        exclude_id: int | None = None,
    ) -> None:
        for field, value in (("username", username), ("email", email)):
            if value is None:
                continue
            stmt = select(User.id).where(getattr(User, field) == value)
            if exclude_id is not None:
                stmt = stmt.where(User.id != exclude_id)
            if self.db.scalar(stmt.limit(1)) is not None:
                raise CustomException(
                    ExceptionType.CONFLICT, f"{field.capitalize()} already exists"
                )

    # -------------------------------------------------------------------- SSO
    def sync_sso_user(self, claims: dict[str, Any]) -> User:
        """Find (or create on first login) the local user behind a Keycloak token.

        Matching order: sso_sub -> verified email of a not-yet-linked account -> create.
        """
        sub = claims["sub"]
        email = (claims.get("email") or "").lower() or None
        user = self.db.scalar(select(User).where(User.sso_sub == sub))
        if user is None and email and claims.get("email_verified"):
            user = self.db.scalar(select(User).where(User.email == email, User.sso_sub.is_(None)))
            if user is not None:
                user.sso_sub = sub
        if user is None:
            if not settings.KEYCLOAK_AUTO_CREATE_USER:
                raise CustomException(ExceptionType.FORBIDDEN, "Account is not registered")
            email_taken = email is not None and self.db.scalar(
                select(User.id).where(User.email == email).limit(1)
            )
            user = User(
                username=self._available_username(claims.get("preferred_username") or email or sub),
                email=None if email_taken else email,
                auth_provider=AuthProvider.KEYCLOAK,
                sso_sub=sub,
                roles=[],
                is_active=True,
            )
            self.db.add(user)

        profile = {
            "full_name": claims.get("name"),
            "first_name": claims.get("given_name"),
            "last_name": claims.get("family_name"),
        }
        for field, value in profile.items():
            if value and getattr(user, field) != value:
                setattr(user, field, value)

        if user in self.db.new or self.db.is_modified(user):
            try:
                self._save(user, commit=True)
            except IntegrityError:
                # Another request created this user concurrently
                self.db.rollback()
                user = self.db.scalar(select(User).where(User.sso_sub == sub))
                if user is None:
                    raise
        return user

    def _available_username(self, wanted: str) -> str:
        base = re.sub(r"[^A-Za-z0-9_.@-]", "", wanted)[:140] or "user"
        username = base
        while self.db.scalar(select(User.id).where(User.username == username).limit(1)):
            username = f"{base}-{secrets.token_hex(3)}"
        return username

    # ------------------------------------------------------------------- seed
    def ensure_superuser(
        self, username: str, email: str | None, password: str
    ) -> tuple[User, bool]:
        """Create the first admin if it does not exist. Returns (user, created)."""
        user = self.get_one_by(username=username)
        if user is not None:
            return user, False
        user = self.create(
            {
                "username": username,
                "email": email,
                "password": password,
                "roles": [UserRole.ADMIN.value],
                "is_active": True,
            }
        )
        return user, True
