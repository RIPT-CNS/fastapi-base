import base64

from tests.conftest import PASSWORD, bearer, create_user, login


def test_health_check(client):
    assert client.get("/api/health-check").json()["success"] is True
    response = client.get("/api/health-check/ready")
    assert response.status_code == 200
    assert response.headers["x-request-id"]


def test_login_and_me(client, normal_user):
    tokens = login(client, normal_user.username)
    assert tokens["token_type"] == "Bearer"
    assert tokens["expires_in"] > 0

    response = client.get("/api/auth/me", headers=bearer(tokens["access_token"]))
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"]["username"] == normal_user.username
    assert body["data"]["roles"] == ["user"]
    assert "hashed_password" not in body["data"]


def test_login_with_email(client, normal_user):
    assert login(client, normal_user.email)["access_token"]


def test_login_wrong_password(client, normal_user):
    response = client.post(
        "/api/auth/login", json={"username": normal_user.username, "password": "wrong-pass"}
    )
    assert response.status_code == 401
    assert response.json() == {
        "http_code": 401,
        "success": False,
        "message": "Incorrect username or password",
        "errors": None,
    }


def test_inactive_user_cannot_login(client):
    create_user("sleepy", is_active=False)
    response = client.post("/api/auth/login", json={"username": "sleepy", "password": PASSWORD})
    assert response.status_code == 403


def test_oauth2_form_token(client, normal_user):
    response = client.post(
        "/api/auth/token", data={"username": normal_user.username, "password": PASSWORD}
    )
    assert response.status_code == 200
    assert response.json()["access_token"]


def test_not_authenticated(client):
    response = client.get("/api/auth/me")
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_garbage_token(client):
    assert client.get("/api/auth/me", headers=bearer("not-a-jwt")).status_code == 401


def test_refresh_token(client, normal_user):
    tokens = login(client, normal_user.username)
    response = client.post("/api/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert response.status_code == 200
    new_access = response.json()["data"]["access_token"]
    assert client.get("/api/auth/me", headers=bearer(new_access)).status_code == 200


def test_token_types_are_not_interchangeable(client, normal_user):
    tokens = login(client, normal_user.username)
    assert client.get("/api/auth/me", headers=bearer(tokens["refresh_token"])).status_code == 401
    response = client.post("/api/auth/refresh", json={"refresh_token": tokens["access_token"]})
    assert response.status_code == 401


def test_logout_revokes_all_tokens(client, normal_user):
    tokens = login(client, normal_user.username)
    headers = bearer(tokens["access_token"])
    assert client.post("/api/auth/logout", headers=headers).status_code == 200
    assert client.get("/api/auth/me", headers=headers).status_code == 401
    response = client.post("/api/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert response.status_code == 401


def test_change_password(client, normal_user):
    old_tokens = login(client, normal_user.username)
    response = client.post(
        "/api/auth/change-password",
        json={"current_password": PASSWORD, "new_password": "NewPassword@456"},
        headers=bearer(old_tokens["access_token"]),
    )
    assert response.status_code == 200
    new_access = response.json()["data"]["access_token"]
    assert client.get("/api/auth/me", headers=bearer(old_tokens["access_token"])).status_code == 401
    assert client.get("/api/auth/me", headers=bearer(new_access)).status_code == 200
    assert login(client, normal_user.username, "NewPassword@456")["access_token"]


def test_update_me(client, user_headers):
    response = client.patch(
        "/api/auth/me",
        json={"full_name": "Nguyen Van A", "dob": "1990-01-31"},
        headers=user_headers,
    )
    assert response.status_code == 200
    assert response.json()["data"]["full_name"] == "Nguyen Van A"
    assert response.json()["data"]["dob"] == "1990-01-31"


def test_basic_auth(client, normal_user):
    credentials = base64.b64encode(f"{normal_user.username}:{PASSWORD}".encode()).decode()
    response = client.get("/api/auth/me", headers={"Authorization": f"Basic {credentials}"})
    assert response.status_code == 200
    assert response.json()["data"]["username"] == normal_user.username

    wrong = base64.b64encode(f"{normal_user.username}:nope".encode()).decode()
    assert (
        client.get("/api/auth/me", headers={"Authorization": f"Basic {wrong}"}).status_code == 401
    )


def test_register(client):
    payload = {"username": "newbie", "email": "Newbie@Example.com", "password": PASSWORD}
    response = client.post("/api/auth/register", json=payload)
    assert response.status_code == 201
    data = response.json()["data"]
    assert data["email"] == "newbie@example.com"
    assert data["roles"] == ["user"]

    assert client.post("/api/auth/register", json=payload).status_code == 409


def test_validation_error_format(client):
    response = client.post("/api/auth/register", json={"username": "x", "password": "short"})
    assert response.status_code == 422
    body = response.json()
    assert body["success"] is False
    fields = {error["field"] for error in body["errors"]}
    assert {"username", "email", "password"} <= fields
