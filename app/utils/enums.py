from enum import StrEnum


class UserRole(StrEnum):
    """Role names. Keep them identical to Keycloak realm/client role names."""

    ADMIN = "admin"
    USER = "user"
    GUEST = "guest"


class UserGender(StrEnum):
    MALE = "male"
    FEMALE = "female"
    OTHER = "other"


class AuthProvider(StrEnum):
    LOCAL = "local"
    KEYCLOAK = "keycloak"
