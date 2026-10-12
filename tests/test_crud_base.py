"""BaseService + CRUDRouter on a generic resource (tests/crud_resources.py)."""

import pytest

URL = "/api/test-items"


@pytest.fixture
def items(client, user_headers):
    rows = [
        {"name": "Apple", "price": 10, "category": "fruit", "tags": ["red", "sweet"]},
        {"name": "Banana", "price": 5, "category": "fruit", "tags": ["yellow"]},
        {"name": "Carrot", "price": 3, "category": "vegetable", "tags": ["orange"]},
        {"name": "100% Juice", "price": 20, "category": None, "is_active": False},
    ]
    created = []
    for row in rows:
        response = client.post(URL, json=row, headers=user_headers)
        assert response.status_code == 201, response.text
        created.append(response.json()["data"])
    return created


def names(response) -> list[str]:
    assert response.status_code == 200, response.text
    return [item["name"] for item in response.json()["data"]]


def test_list_is_public_and_write_requires_login(client):
    assert client.get(URL).status_code == 200
    assert client.post(URL, json={"name": "x"}).status_code == 401


def test_create_sets_defaults_and_timestamps(items):
    item = items[0]
    assert item["id"] == 1
    assert item["is_active"] is True
    assert item["created_at"] and item["updated_at"]


def test_filters(client, items):
    assert names(
        client.get(URL, params={"price__gte": 5, "price__lte": 10, "sort_by": "price"})
    ) == [
        "Apple",
        "Banana",
    ]
    assert names(client.get(URL, params={"category": "vegetable"})) == ["Carrot"]
    assert set(names(client.get(URL, params={"category__in": ["vegetable", "fruit"]}))) == {
        "Apple",
        "Banana",
        "Carrot",
    }
    assert names(client.get(URL, params={"category__isnull": True})) == ["100% Juice"]
    assert names(client.get(URL, params={"tags": "yellow"})) == ["Banana"]
    assert names(client.get(URL, params={"is_active": False})) == ["100% Juice"]
    # LIKE input is escaped: "%" is literal
    assert names(client.get(URL, params={"name__like": "0%"})) == ["100% Juice"]


def test_search_and_sort(client, items):
    assert names(client.get(URL, params={"search": "VEGET"})) == ["Carrot"]
    assert names(client.get(URL, params={"sort_by": "name", "order": "asc", "page_size": 2})) == [
        "100% Juice",
        "Apple",
    ]
    # default: id desc
    assert names(client.get(URL))[0] == "100% Juice"
    assert client.get(URL, params={"sort_by": "tags"}).status_code == 422


def test_pagination(client, items):
    body = client.get(URL, params={"page": 2, "page_size": 3}).json()
    assert len(body["data"]) == 1
    assert body["metadata"] == {"page": 2, "page_size": 3, "total": 4, "total_pages": 2}


def test_patch_is_partial_put_is_full(client, items, user_headers):
    item_id = items[0]["id"]
    response = client.patch(f"{URL}/{item_id}", json={"price": 99}, headers=user_headers)
    data = response.json()["data"]
    assert (data["name"], data["price"], data["category"]) == ("Apple", 99, "fruit")
    assert data["updated_at"] > items[0]["updated_at"]

    full = {"name": "Green apple", "price": 1, "category": None, "tags": [], "is_active": True}
    data = client.put(f"{URL}/{item_id}", json=full, headers=user_headers).json()["data"]
    assert (data["name"], data["category"], data["tags"]) == ("Green apple", None, [])

    # PUT writes every field: a missing non-nullable column is rejected
    response = client.put(f"{URL}/{item_id}", json={"name": "x"}, headers=user_headers)
    assert response.status_code == 400


def test_soft_delete(client, items, user_headers, admin_headers):
    item_id = items[1]["id"]
    assert client.delete(f"{URL}/{item_id}", headers=user_headers).status_code == 403
    assert client.delete(f"{URL}/{item_id}", headers=admin_headers).status_code == 200
    assert client.get(f"{URL}/{item_id}").status_code == 404
    assert "Banana" not in names(client.get(URL))
    assert (
        client.patch(f"{URL}/{item_id}", json={"price": 1}, headers=user_headers).status_code == 404
    )

    from app.core.database import SessionLocal
    from tests.crud_resources import Item

    with SessionLocal() as db:
        assert db.get(Item, item_id).deleted_at is not None


def test_not_found(client, user_headers):
    response = client.get(f"{URL}/999")
    assert response.status_code == 404
    assert response.json()["message"] == "Item not found"
    assert client.get(f"{URL}/abc").status_code == 422
