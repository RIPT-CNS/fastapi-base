from tests.conftest import PASSWORD, bearer, create_user, login


def test_users_require_permission(client, user_headers):
    assert client.get("/api/v1/users").status_code == 401
    assert client.get("/api/v1/users", headers=user_headers).status_code == 403
    assert client.post("/api/v1/users", json={}, headers=user_headers).status_code == 403


def test_current_version_alias(client, admin_headers):
    assert client.get("/api/users", headers=admin_headers).status_code == 200


def test_admin_user_crud(client, admin_headers):
    payload = {
        "username": "alice",
        "email": "alice@example.com",
        "password": PASSWORD,
        "full_name": "Alice",
    }
    response = client.post("/api/v1/users", json=payload, headers=admin_headers)
    assert response.status_code == 201, response.text
    user = response.json()["data"]
    assert user["roles"] == ["user"]
    assert user["auth_provider"] == "local"

    response = client.get(f"/api/v1/users/{user['id']}", headers=admin_headers)
    assert response.json()["data"]["full_name"] == "Alice"

    # PATCH only touches the fields sent
    response = client.patch(
        f"/api/v1/users/{user['id']}", json={"phone": "0900000000"}, headers=admin_headers
    )
    assert response.status_code == 200
    assert response.json()["data"]["full_name"] == "Alice"
    assert response.json()["data"]["is_active"] is True

    # Password set by admin is hashed and usable
    client.patch(
        f"/api/v1/users/{user['id']}", json={"password": "Changed@789"}, headers=admin_headers
    )
    assert login(client, "alice", "Changed@789")["access_token"]

    # PUT is disabled for users
    assert (
        client.put(f"/api/v1/users/{user['id']}", json={}, headers=admin_headers).status_code == 405
    )

    response = client.delete(f"/api/v1/users/{user['id']}", headers=admin_headers)
    assert response.status_code == 200
    assert client.get(f"/api/v1/users/{user['id']}", headers=admin_headers).status_code == 404


def test_duplicate_user(client, admin_headers, normal_user):
    payload = {"username": normal_user.username, "password": PASSWORD}
    response = client.post("/api/v1/users", json=payload, headers=admin_headers)
    assert response.status_code == 409
    assert response.json()["message"] == "Username already exists"

    payload = {"username": "other", "email": normal_user.email, "password": PASSWORD}
    assert client.post("/api/v1/users", json=payload, headers=admin_headers).status_code == 409


def test_list_users_filter_search_sort(client, admin_headers):
    create_user("bob", full_name="Bob Builder")
    create_user("carol", full_name="Carol", is_active=False)
    create_user("dave", roles=["user", "editor"])

    def list_users(**params):
        response = client.get("/api/v1/users", params=params, headers=admin_headers)
        assert response.status_code == 200, response.text
        return response.json()

    body = list_users(page_size=2, sort_by="username", order="asc")
    assert [u["username"] for u in body["data"]] == ["admin1", "bob"]
    assert body["metadata"] == {"page": 1, "page_size": 2, "total": 4, "total_pages": 2}

    assert [u["username"] for u in list_users(search="builder")["data"]] == ["bob"]
    assert [u["username"] for u in list_users(is_active="false")["data"]] == ["carol"]
    assert [u["username"] for u in list_users(roles="editor")["data"]] == ["dave"]
    assert list_users(roles__in=["admin", "editor"])["metadata"]["total"] == 2


def test_list_users_invalid_params(client, admin_headers):
    response = client.get(
        "/api/v1/users", params={"sort_by": "hashed_password"}, headers=admin_headers
    )
    assert response.status_code == 422
    response = client.get("/api/v1/users", params={"page_size": 1000}, headers=admin_headers)
    assert response.status_code == 422


def test_basic_auth_admin_access(client, admin_user):
    import base64

    credentials = base64.b64encode(f"{admin_user.username}:{PASSWORD}".encode()).decode()
    response = client.get("/api/v1/users", headers={"Authorization": f"Basic {credentials}"})
    assert response.status_code == 200


def test_deactivated_user_token_rejected(client, admin_headers, normal_user):
    tokens = login(client, normal_user.username)
    client.patch(
        f"/api/v1/users/{normal_user.id}", json={"is_active": False}, headers=admin_headers
    )
    assert client.get("/api/auth/me", headers=bearer(tokens["access_token"])).status_code == 403
