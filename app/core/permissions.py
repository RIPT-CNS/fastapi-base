"""Role -> permission mapping (RBAC).

Permissions are "<resource>:<action>" strings. A BaseAPI with permission_prefix = "product"
checks product:read, product:create, product:update, product:delete, product:import,
product:export (the route groups of app.core.base_api).

Wildcards: "*" = everything, "product:*" = every action on product.
Roles can come from the local DB (users.roles) or from Keycloak (realm/client roles),
so name roles here exactly like in Keycloak.
"""

from collections.abc import Iterable

from app.utils.enums import RouteGroup, UserRole

ALL_PERMISSIONS = "*"


def permission(resource: str, action: RouteGroup | str) -> str:
    """permission("product", RouteGroup.READ) -> "product:read"."""
    return f"{resource}:{action}"


ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    UserRole.ADMIN: frozenset({ALL_PERMISSIONS}),
    UserRole.USER: frozenset(),
    UserRole.GUEST: frozenset(),
    # Example: a role that may view (but not modify) users
    # "manager": frozenset({permission("user", RouteGroup.READ)}),
}


def get_permissions(roles: Iterable[str]) -> set[str]:
    permissions: set[str] = set()
    for role in roles:
        permissions |= ROLE_PERMISSIONS.get(role, frozenset())
    return permissions


def has_permission(roles: Iterable[str], required: str) -> bool:
    granted = get_permissions(roles)
    if ALL_PERMISSIONS in granted or required in granted:
        return True
    resource = required.split(":", 1)[0]
    return permission(resource, ALL_PERMISSIONS) in granted
