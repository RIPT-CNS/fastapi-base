import time

from app.core.database import SessionLocal
from app.models import User
from tests.conftest import bearer, create_user


def test_sso_user_is_provisioned_on_first_request(client, kc_token):
    response = client.get("/api/auth/me", headers=bearer(kc_token()))
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["username"] == "kc.user"
    assert data["auth_provider"] == "keycloak"
    assert data["full_name"] == "KC User"
    assert data["roles"] == ["user"]

    # Second request reuses the same local user
    assert client.get("/api/auth/me", headers=bearer(kc_token())).json()["data"]["id"] == data["id"]
    with SessionLocal() as db:
        assert db.query(User).count() == 1


def test_roles_from_token_are_enforced(client, kc_token):
    user_token = kc_token(realm_access={"roles": ["user"]})
    assert client.get("/api/v1/users", headers=bearer(user_token)).status_code == 403

    admin_token = kc_token(realm_access={"roles": ["admin"]})
    assert client.get("/api/v1/users", headers=bearer(admin_token)).status_code == 200

    client_role_token = kc_token(
        realm_access={"roles": []}, resource_access={"test-backend": {"roles": ["admin"]}}
    )
    assert client.get("/api/v1/users", headers=bearer(client_role_token)).status_code == 200


def test_verified_email_links_existing_local_account(client, kc_token):
    local = create_user("existing", email="kc.user@example.com")
    data = client.get("/api/auth/me", headers=bearer(kc_token())).json()["data"]
    assert data["id"] == local.id
    assert data["username"] == "existing"


def test_unverified_email_does_not_link(client, kc_token):
    local = create_user("existing", email="kc.user@example.com")
    data = client.get("/api/auth/me", headers=bearer(kc_token(email_verified=False))).json()["data"]
    assert data["id"] != local.id
    assert data["email"] is None


def test_invalid_keycloak_tokens(client, kc_token):
    now = int(time.time())
    for token in (
        kc_token(aud="another-client"),
        kc_token(iss="http://evil.example/realms/test-realm"),
        kc_token(typ="ID"),
        kc_token(exp=now - 60, iat=now - 600),
        kc_token(sub=None),
    ):
        assert client.get("/api/auth/me", headers=bearer(token)).status_code == 401


def test_locally_deactivated_sso_user_is_rejected(client, kc_token):
    user_id = client.get("/api/auth/me", headers=bearer(kc_token())).json()["data"]["id"]
    with SessionLocal() as db:
        db.get(User, user_id).is_active = False
        db.commit()
    assert client.get("/api/auth/me", headers=bearer(kc_token())).status_code == 403


def test_sso_config(client):
    data = client.get("/api/auth/sso/config").json()["data"]
    assert data["issuer"] == "http://sso.example.test/realms/test-realm"
    assert data["client_id"] == "test-frontend"
    assert data["authorization_endpoint"].startswith("http://sso.example.test/")


def test_sso_authorize_redirects_to_keycloak(client):
    response = client.get("/api/auth/sso/authorize", follow_redirects=False)
    assert response.status_code == 307
    location = response.headers["location"]
    assert location.startswith(
        "http://sso.example.test/realms/test-realm/protocol/openid-connect/auth"
    )
    assert "code_challenge=" in location
    assert "sso_state" in response.cookies
