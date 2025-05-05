import enum


class UserRole(enum.Enum):
    ADMIN = "admin"
    GUEST = "guest"

class AuthMethod(enum.Enum):
    BASIC = "BASIC"
    KEYCLOAK = "KEYCLOAK"
    OAUTH2 = "OAUTH2"
