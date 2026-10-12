"""BaseAPI + BaseService on generic resources (tests/crud_resources.py)."""

import json

import pytest

from app.core.database import SessionLocal
from tests.crud_resources import Item

URL = "/api/test-items"  # fixtures categories / items: tests/conftest.py


def names(response) -> list[str]:
    assert response.status_code == 200, response.text
    return [item["name"] for item in response.json()["data"]]


# ------------------------------------------------------------------- read
def test_read_routes(client, items):
    assert [i["id"] for i in items] == [1, 2, 3, 4]
    assert client.get(f"{URL}/1").json()["data"]["name"] == "Apple"
    assert names(client.get(f"{URL}/many", params={"ids": [3, 1]})) == ["Apple", "Carrot"]
    assert names(client.get(f"{URL}/list", params={"sort": "name"})) == [
        "100% Juice", "Apple", "Banana", "Carrot",
    ]  # fmt: skip
    assert client.get(f"{URL}/count", params={"price__gte": 5}).json()["data"] == 3
    first = client.get(f"{URL}/first", params={"sort": "price"}).json()["data"]
    assert first["name"] == "Carrot"
    assert client.get(f"{URL}/first", params={"name": "nope"}).status_code == 404

    body = client.get(URL, params={"page": 2, "page_size": 3}).json()
    assert body["metadata"] == {"page": 2, "page_size": 3, "total": 4, "total_pages": 2}
    assert len(body["data"]) == 1


def test_shorthand_filters(client, items, categories):
    assert names(client.get(URL, params={"price__between": "3,5", "sort": "price"})) == [
        "Carrot",
        "Banana",
    ]
    assert names(client.get(URL, params={"category.name": "vegetable"})) == ["Carrot"]
    assert set(names(client.get(URL, params={"category.name__in": ["fruit", "vegetable"]}))) == {
        "Apple", "Banana", "Carrot",
    }  # fmt: skip
    assert names(client.get(URL, params={"category__isnull": "true"})) == ["100% Juice"]
    assert names(client.get(URL, params={"tags": "yellow"})) == ["Banana"]
    assert names(client.get(URL, params={"tags__in": "red,orange", "sort": "name"})) == [
        "Apple",
        "Carrot",
    ]
    assert names(client.get(URL, params={"is_active": "false"})) == ["100% Juice"]
    assert names(client.get(URL, params={"released_on__gte": "2024-02-01"})) == ["Banana"]
    assert names(client.get(URL, params={"name__like": "0%"})) == ["100% Juice"]  # % escaped
    assert names(client.get(URL, params={"name__startswith": "ap"})) == ["Apple"]
    assert names(client.get(URL, params={"sku__ne": "A1", "price__lt": 10, "sort": "name"})) == [
        "Banana",
        "Carrot",
    ]
    # one-to-many from the other side
    response = client.get("/api/test-categories", params={"items.name__like": "carr"})
    assert names(response) == ["vegetable"]


def test_json_filters(client, items):
    filters = [
        {
            "or": [
                {"field": "price", "op": "gte", "value": 20},
                {"field": "category.name", "value": "vegetable"},
            ]
        },
        {"not": {"field": "name", "op": "eq", "value": "Carrot"}},
    ]
    assert names(client.get(URL, params={"filters": json.dumps(filters)})) == ["100% Juice"]
    shorthand_object = {"price__gte": 5, "is_active": True}
    response = client.get(URL, params={"filters": json.dumps(shorthand_object), "sort": "name"})
    assert names(response) == ["Apple", "Banana"]


def test_search_and_sort(client, items):
    assert names(client.get(URL, params={"search": "b1"})) == ["Banana"]  # default: name, sku
    response = client.get(URL, params={"search": "VEGET", "search_fields": "name,category.name"})
    assert names(response) == ["Carrot"]
    response = client.get(URL, params={"sort": "-is_active,-price"})
    assert names(response) == ["Apple", "Banana", "Carrot", "100% Juice"]


@pytest.mark.parametrize(
    "params",
    [
        {"unknown": "x"},
        {"price__foo": 1},
        {"price": "abc"},
        {"price__between": "1"},
        {"category": "x"},
        {"filters": "not json"},
        {"filters": '[{"field": "price", "op": "regex", "value": 1}]'},
        {"sort": "nope"},
        {"search": "x", "search_fields": "nope"},
        {"a.b.c.d.e": 1},
    ],
)
def test_invalid_queries(client, items, params):
    response = client.get(URL, params=params)
    assert response.status_code == 400, response.text
    assert response.json()["success"] is False


# ----------------------------------------------------------------- create
def test_create_validation(client, user_headers):
    response = client.post(URL, json={"name": "A", "price": -1}, headers=user_headers)
    assert response.status_code == 422
    assert {e["field"] for e in response.json()["errors"]} == {"name", "price"}
    assert client.post(f"{URL}/many", json=[], headers=user_headers).status_code == 422


# ----------------------------------------------------------------- update
def test_update_one(client, items, user_headers):
    response = client.patch(f"{URL}/1", json={"price": 99}, headers=user_headers)
    data = response.json()["data"]
    assert (data["name"], data["price"], data["sku"]) == ("Apple", 99, "A1")
    assert data["updated_at"] > items[0]["updated_at"]

    full = {"name": "Green apple", "price": 1, "tags": [], "is_active": True}
    data = client.put(f"{URL}/1", json=full, headers=user_headers).json()["data"]
    # PUT writes every field: the ones not sent are reset to the schema defaults
    assert (data["name"], data["sku"], data["category_id"]) == ("Green apple", None, None)
    # ... so a missing non-nullable column is rejected
    assert client.put(f"{URL}/1", json={"name": "x2"}, headers=user_headers).status_code == 400


def test_update_many(client, items, user_headers):
    payload = [{"id": 1, "price": 11}, {"id": 2, "name": "Big banana"}]
    response = client.patch(f"{URL}/many", json=payload, headers=user_headers)
    data = response.json()["data"]
    assert [(d["id"], d["name"], d["price"]) for d in data] == [
        (1, "Apple", 11),
        (2, "Big banana", 5),
    ]
    response = client.patch(f"{URL}/many", json=[{"id": 1}, {"id": 99}], headers=user_headers)
    assert response.status_code == 404
    assert "99" in response.json()["message"]


def test_update_all(client, items, user_headers):
    response = client.patch(f"{URL}/all", json={"is_active": False}, headers=user_headers)
    assert response.status_code == 400  # no filter -> needs confirm

    response = client.patch(
        f"{URL}/all", params={"category.name": "fruit"}, json={"price": 1}, headers=user_headers
    )
    assert response.json()["data"] == {"count": 2}
    assert client.get(f"{URL}/count", params={"price": 1}).json()["data"] == 2

    response = client.patch(
        f"{URL}/all", params={"confirm": "true"}, json={"is_active": True}, headers=user_headers
    )
    assert response.json()["data"] == {"count": 4}


# ----------------------------------------------------------------- delete
def test_delete(client, items, user_headers, admin_headers):
    assert client.delete(f"{URL}/1", headers=user_headers).status_code == 403  # roles=["admin"]
    assert client.delete(f"{URL}/1", headers=admin_headers).status_code == 200
    assert client.get(f"{URL}/1").status_code == 404

    response = client.delete(f"{URL}/many", params={"ids": [2, 3]}, headers=admin_headers)
    assert response.json()["data"] == {"count": 2}
    assert (
        client.delete(f"{URL}/many", params={"ids": [2]}, headers=admin_headers).status_code == 404
    )

    assert client.delete(f"{URL}/all", headers=admin_headers).status_code == 400
    response = client.delete(f"{URL}/all", params={"confirm": True}, headers=admin_headers)
    assert response.json()["data"] == {"count": 1}
    assert client.get(f"{URL}/count").json()["data"] == 0

    # soft delete: rows still in the table
    with SessionLocal() as db:
        assert db.query(Item).filter(Item.deleted_at.is_not(None)).count() == 4


# ----------------------------------------------------------------- access
def test_route_level_access(client, items, user_headers):
    assert client.get(URL).status_code == 200  # read: auth=False
    assert client.get(f"{URL}/export").status_code == 200  # export: auth=False
    assert client.post(URL, json={"name": "xx"}).status_code == 401
    assert client.get(f"{URL}/import/template").status_code == 401


def test_model_level_roles(client, items, user_headers, admin_headers):
    url = "/api/test-admin-items"
    assert client.get(url).status_code == 401
    assert client.get(url, headers=user_headers).status_code == 403
    assert client.get(url, headers=admin_headers).json()["metadata"]["total"] == 4


def test_public_api_and_disabled_routes(client):
    response = client.post("/api/test-categories", json={"name": "public"})
    assert response.status_code == 201
    assert client.delete(f"/api/test-categories/{response.json()['data']['id']}").status_code == 200

    paths = client.app.openapi()["paths"]
    assert "/api/test-categories/all" in paths  # PUT/PATCH all still enabled
    assert "delete" not in paths["/api/test-categories/all"]
    assert "/api/test-categories/import" not in paths
    assert "/api/test-categories/export" in paths
    assert "/api/test-admin-items/export" not in paths  # enable_export = False
    # no update_schema -> no PUT/PATCH routes
    assert set(paths["/api/test-admin-items/{item_id}"]) == {"get", "delete"}


def test_route_keys_never_shadow_groups():
    from app.core.base_api import ROUTE_GROUPS, BaseAPI, RouteConfig
    from app.utils.enums import Route, RouteGroup
    from tests.crud_resources import ItemCreate, ItemResponse, ItemService

    assert not set(Route) & set(RouteGroup)
    assert set(ROUTE_GROUPS) == set(Route)

    class OnlyCreateOneIsAdmin(BaseAPI):
        prefix = "/x"
        service = ItemService
        response_schema = ItemResponse
        create_schema = ItemCreate
        route_config = {Route.CREATE_ONE: RouteConfig(roles=["admin"])}

    api = OnlyCreateOneIsAdmin()
    assert api.route_config_for(Route.CREATE_ONE).roles == ["admin"]
    assert api.route_config_for(Route.CREATE_MANY).roles is None
