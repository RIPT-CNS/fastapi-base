"""Generic CRUD router: declare a service + schemas, get a full REST resource.

    router = CRUDRouter(
        prefix="/products",
        service=ProductService,
        response_schema=ProductResponse,
        create_schema=ProductCreateRequest,
        update_schema=ProductUpdateRequest,
        permission_prefix="product",          # product:read/create/update/delete
    )

Generated routes:
    GET    /products          list: page, page_size, sort_by, order, search, filters
    GET    /products/{id}     get
    POST   /products          create
    PUT    /products/{id}     full update   (update_schema, unset fields -> defaults)
    PATCH  /products/{id}     partial update (only fields sent)
    DELETE /products/{id}     delete (soft delete if the model has SoftDeleteMixin)

Access control, per action ("list", "get", "create", "update", "patch", "delete"):
    permissions={"list": None}                  -> public
    permissions={"delete": ["admin"]}           -> any of these roles
    permissions={"create": PermissionRequired("product:create")}  -> any dependency
    otherwise permission_prefix if given, else login required (auth_required=True).
"""

from collections.abc import Callable, Mapping, Sequence
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, Field, create_model
from sqlalchemy import Column
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.dialects.postgresql import ARRAY

from app.schemas.sche_base import ListQueryParams
from app.schemas.sche_response import BaseResponse, DataResponse, PageResponse
from app.services.srv_base import BaseService
from app.utils.login_manager import PermissionRequired, RoleRequired, get_current_user

ACTIONS = ("list", "get", "create", "update", "patch", "delete")
ACTION_PERMISSIONS = {
    "list": "read",
    "get": "read",
    "create": "create",
    "update": "update",
    "patch": "update",
    "delete": "delete",
}

PermissionSpec = Sequence[str] | Callable[..., Any] | None


def _python_type(column: Column) -> type:
    column_type = column.type.item_type if isinstance(column.type, ARRAY) else column.type
    try:
        return column_type.python_type
    except NotImplementedError:
        return str


def build_list_params_model(service: type[BaseService]) -> type[ListQueryParams]:
    """Query-string model for the list endpoint, documented in OpenAPI."""
    columns = sa_inspect(service.model).columns
    fields: dict[str, Any] = {
        "sort_by": (
            Literal[service.get_sort_fields()] | None,
            Field(None, description=f"Default: {service.default_sort_by}"),
        ),
        "order": (Literal["asc", "desc"], service.default_order),
    }
    if service.search_fields:
        fields["search"] = (
            str | None,
            Field(None, description=f"Search in: {', '.join(service.search_fields)}"),
        )
    for name, operators in service.get_filter_fields().items():
        value_type = _python_type(columns[name])
        for op in operators:
            if op in ("in", "not_in"):
                annotation = list[value_type]
            elif op == "isnull":
                annotation = bool
            elif op == "like":
                annotation = str
            else:
                annotation = value_type
            param = name if op == "eq" else f"{name}__{op}"
            fields[param] = (annotation | None, Field(None, description=f"{name} {op}"))
    return create_model(f"{service.model.__name__}ListParams", __base__=ListQueryParams, **fields)


class CRUDRouter(APIRouter):
    def __init__(
        self,
        *,
        prefix: str,
        service: type[BaseService],
        response_schema: type[BaseModel],
        create_schema: type[BaseModel] | None = None,
        update_schema: type[BaseModel] | None = None,
        tags: list[str] | None = None,
        auth_required: bool = True,
        permission_prefix: str | None = None,
        permissions: Mapping[str, PermissionSpec] | None = None,
        exclude: Sequence[str] = (),
        **router_kwargs: Any,
    ) -> None:
        super().__init__(prefix=prefix, tags=tags or [service.model.__name__], **router_kwargs)
        self.service = service
        self.response_schema = response_schema
        self.create_schema = create_schema
        self.update_schema = update_schema
        self.auth_required = auth_required
        self.permission_prefix = permission_prefix
        self.permissions = dict(permissions or {})
        if unknown := (set(self.permissions) | set(exclude)) - set(ACTIONS):
            raise ValueError(f"Unknown CRUD actions: {unknown}. Valid: {ACTIONS}")

        self._name = service.model.__name__
        self._id_type = _python_type(sa_inspect(service.model).columns["id"])

        for action in ACTIONS:
            if action in exclude:
                continue
            if action == "create" and create_schema is None:
                continue
            if action in ("update", "patch") and update_schema is None:
                continue
            getattr(self, f"_add_{action}_route")(self._dependencies(action))

    def _dependencies(self, action: str) -> list[Any]:
        if action in self.permissions:
            spec = self.permissions[action]
            if spec is None:
                return []
            if isinstance(spec, str):
                spec = (spec,)
            if callable(spec):
                return [Depends(spec)]
            return [Depends(RoleRequired(*spec))]
        if self.permission_prefix:
            permission = f"{self.permission_prefix}:{ACTION_PERMISSIONS[action]}"
            return [Depends(PermissionRequired(permission))]
        return [Depends(get_current_user)] if self.auth_required else []

    # ----------------------------------------------------------------- routes
    def _add_list_route(self, dependencies: list[Any]) -> None:
        service_cls, schema = self.service, self.response_schema
        params_model = build_list_params_model(service_cls)
        response_model = PageResponse[schema]

        def list_items(
            params: Annotated[params_model, Query()],
            service: Annotated[service_cls, Depends()],
        ) -> Any:
            items, metadata = service.get_by_filter(
                pagination_params=params.pagination(),
                sort_params=params.sorting(),
                filters=params.filters(),
                search=getattr(params, "search", None),
            )
            return response_model(
                data=[schema.model_validate(item) for item in items], metadata=metadata
            )

        self.add_api_route(
            "",
            list_items,
            methods=["GET"],
            response_model=response_model,
            dependencies=dependencies,
            summary=f"List {self._name}",
        )

    def _add_get_route(self, dependencies: list[Any]) -> None:
        service_cls, schema, id_type = self.service, self.response_schema, self._id_type
        response_model = DataResponse[schema]

        def get_item(item_id: id_type, service: Annotated[service_cls, Depends()]) -> Any:
            return response_model(data=schema.model_validate(service.get_by_id(item_id)))

        self.add_api_route(
            "/{item_id}",
            get_item,
            methods=["GET"],
            response_model=response_model,
            dependencies=dependencies,
            summary=f"Get {self._name}",
        )

    def _add_create_route(self, dependencies: list[Any]) -> None:
        service_cls, schema, create_schema = self.service, self.response_schema, self.create_schema
        response_model = DataResponse[schema]

        def create_item(payload: create_schema, service: Annotated[service_cls, Depends()]) -> Any:
            obj = service.create(payload)
            return response_model(
                http_code=status.HTTP_201_CREATED, data=schema.model_validate(obj)
            )

        self.add_api_route(
            "",
            create_item,
            methods=["POST"],
            status_code=status.HTTP_201_CREATED,
            response_model=response_model,
            dependencies=dependencies,
            summary=f"Create {self._name}",
        )

    def _add_update_route(self, dependencies: list[Any]) -> None:
        service_cls, schema, id_type = self.service, self.response_schema, self._id_type
        update_schema = self.update_schema
        response_model = DataResponse[schema]

        def update_item(
            item_id: id_type, payload: update_schema, service: Annotated[service_cls, Depends()]
        ) -> Any:
            obj = service.update_by_id(item_id, payload)
            return response_model(data=schema.model_validate(obj))

        self.add_api_route(
            "/{item_id}",
            update_item,
            methods=["PUT"],
            response_model=response_model,
            dependencies=dependencies,
            summary=f"Replace {self._name}",
        )

    def _add_patch_route(self, dependencies: list[Any]) -> None:
        service_cls, schema, id_type = self.service, self.response_schema, self._id_type
        update_schema = self.update_schema
        response_model = DataResponse[schema]

        def patch_item(
            item_id: id_type, payload: update_schema, service: Annotated[service_cls, Depends()]
        ) -> Any:
            obj = service.partial_update_by_id(item_id, payload)
            return response_model(data=schema.model_validate(obj))

        self.add_api_route(
            "/{item_id}",
            patch_item,
            methods=["PATCH"],
            response_model=response_model,
            dependencies=dependencies,
            summary=f"Update {self._name}",
        )

    def _add_delete_route(self, dependencies: list[Any]) -> None:
        service_cls, id_type = self.service, self._id_type

        def delete_item(item_id: id_type, service: Annotated[service_cls, Depends()]) -> Any:
            service.delete_by_id(item_id)
            return BaseResponse(message=f"{self._name} deleted")

        self.add_api_route(
            "/{item_id}",
            delete_item,
            methods=["DELETE"],
            response_model=BaseResponse,
            dependencies=dependencies,
            summary=f"Delete {self._name}",
        )
