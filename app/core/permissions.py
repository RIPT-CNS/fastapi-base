"""Role -> permission mapping (RBAC).

Permissions are "<resource>:<action>" strings. CRUDRouter(permission_prefix="product")
checks product:read (list/get), product:create, product:update (PUT/PATCH), product:delete.

Wildcards: "*" = everything, "product:*" = every action on product.
Roles can come from the local DB (users.roles) or from Keycloak (realm/client roles),
so name roles here exactly like in Keycloak.
"""

from collections.abc import Iterable

from app.utils.enums import UserRole

ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    UserRole.ADMIN: frozenset({"*"}),
    UserRole.USER: frozenset(),
    UserRole.GUEST: frozenset(),
    # Example: a role that may view (but not modify) users
    # "manager": frozenset({"user:read"}),
}


def get_permissions(roles: Iterable[str]) -> set[str]:
    permissions: set[str] = set()
    for role in roles:
        permissions |= ROLE_PERMISSIONS.get(role, frozenset())
    return permissions


def has_permission(roles: Iterable[str], permission: str) -> bool:
    granted = get_permissions(roles)
    if "*" in granted or permission in granted:
        return True
    resource = permission.split(":", 1)[0]
    return f"{resource}:*" in granted
