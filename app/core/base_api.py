"""BaseAPI: declare a class -> full REST resource (CRUD, bulk, dynamic query, Excel import/export).

    class ProductAPI(BaseAPI):
        prefix = "/products"
        service = ProductService
        response_schema = ProductResponse
        create_schema = ProductCreateRequest
        update_schema = ProductUpdateRequest

Put it in app/api/vN/api_*.py: it is mounted automatically.

Routes (key: method path)                              group
    count:             GET    /count                   read
    get_first:         GET    /first                   read
    get_list:          GET    /list                    read
    get_many:          GET    /many?ids=1&ids=2        read
    get_page:          GET    ""                       read
    get_one:           GET    /{item_id}               read
    create:            POST   ""                       create
    create_many:       POST   /many                    create
    update_one:        PUT    /{item_id}               update   (full)
    patch_one:         PATCH  /{item_id}               update   (partial)
    update_many:       PUT    /many   [{id, ...}]      update
    patch_many:        PATCH  /many   [{id, ...}]      update
    update_all:        PUT    /all?<filters>           update   (same values for every match)
    patch_all:         PATCH  /all?<filters>           update
    delete_one:        DELETE /{item_id}               delete
    delete_many:       DELETE /many?ids=1&ids=2        delete
    delete_all:        DELETE /all?<filters>           delete
    import_template:   GET    /import/template         import
    import_validate:   POST   /import/validate         import   (dry run, returns row errors)
    import_data:       POST   /import?mode=insert|update|upsert   import
    export:            GET    /export?fields=a,b.c&format=xlsx|csv   export
    export_importable: GET    /export/importable       export   (re-importable format)

Every read/export/bulk route accepts the dynamic query of app.utils.query_builder:
?filters=[...]  ?field__op=value  ?search=&search_fields=  ?sort=-a,b
/all routes refuse to run without filter/search unless ?confirm=true.

Access control, resolved per route (route key first, then its group):
    public = True                    -> no auth at all (see BasePublicAPI)
    RouteConfig(auth=False)          -> this route is public
    RouteConfig(roles=["admin"])     -> any of these roles
    RouteConfig(permissions=[...])   -> all of these permissions
    otherwise the class values: auth_required, roles, permission_prefix ("<prefix>:<group>")
"""

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Annotated, Any, BinaryIO, ClassVar, Literal

from fastapi import APIRouter, Body, Depends, File, Query, Request, UploadFile, status
from fastapi.responses import Response
from pydantic import BaseModel, create_model
from sqlalchemy import inspect as sa_inspect

from app.core.config import settings
from app.schemas.sche_base import BulkResult, ImportMode, ImportResult, PaginationParams
from app.schemas.sche_response import BaseResponse, DataResponse, PageResponse
from app.services.srv_base import BaseService
from app.utils.excel import (
    CSV_MEDIA_TYPE,
    XLSX_MEDIA_TYPE,
    csv_streaming_response,
    xlsx_file_response,
    xlsx_response,
)
from app.utils.exception_handler import CustomException, ExceptionType
from app.utils.login_manager import PermissionRequired, RoleRequired, get_current_user
from app.utils.query_builder import (
    Condition,
    QuerySpec,
    column_python_type,
    parse_filters,
    split_csv,
    split_key,
)

# (key, method, path, group) - static paths before /{item_id}
ROUTES: tuple[tuple[str, str, str, str], ...] = (
    ("count", "GET", "/count", "read"),
    ("get_first", "GET", "/first", "read"),
    ("get_list", "GET", "/list", "read"),
    ("get_many", "GET", "/many", "read"),
    ("get_page", "GET", "", "read"),
    ("export", "GET", "/export", "export"),
    ("export_importable", "GET", "/export/importable", "export"),
    ("import_template", "GET", "/import/template", "import"),
    ("import_validate", "POST", "/import/validate", "import"),
    ("import_data", "POST", "/import", "import"),
    ("create", "POST", "", "create"),
    ("create_many", "POST", "/many", "create"),
    ("update_many", "PUT", "/many", "update"),
    ("patch_many", "PATCH", "/many", "update"),
    ("update_all", "PUT", "/all", "update"),
    ("patch_all", "PATCH", "/all", "update"),
    ("delete_many", "DELETE", "/many", "delete"),
    ("delete_all", "DELETE", "/all", "delete"),
    ("get_one", "GET", "/{item_id}", "read"),
    ("update_one", "PUT", "/{item_id}", "update"),
    ("patch_one", "PATCH", "/{item_id}", "update"),
    ("delete_one", "DELETE", "/{item_id}", "delete"),
)
ROUTE_GROUPS = {key: group for key, _, _, group in ROUTES}

# Query params that are not shorthand filters
RESERVED_PARAMS = frozenset(
    {"filters", "search", "search_fields", "sort", "page", "page_size", "ids", "fields",
     "confirm", "mode", "format"}
)  # fmt: skip

_XLSX_RESPONSE = {200: {"content": {XLSX_MEDIA_TYPE: {}}, "description": "Excel file"}}
_EXPORT_RESPONSE = {
    200: {"content": {XLSX_MEDIA_TYPE: {}, CSV_MEDIA_TYPE: {}}, "description": "Excel or CSV file"}
}


@dataclass(frozen=True)
class RouteConfig:
    """Per route (key) or per group ("read", "create", "update", "delete", "import", "export").
    None = inherit the class-level value."""

    enabled: bool = True
    auth: bool | None = None
    roles: Sequence[str] | None = None
    permissions: Sequence[str] | None = None
    dependencies: Sequence[Callable[..., Any]] = ()


def query_spec(
    request: Request,
    filters: Annotated[
        str | None,
        Query(
            description='JSON list of conditions, e.g. [{"field":"price","op":"gte","value":10},'
            '{"or":[{"field":"name","op":"like","value":"a"},{"field":"category.name",'
            '"value":"x"}]}]. Shorthand: ?price__gte=10&category.name__in=a,b. Operators: eq, ne,'
            " gt, gte, lt, lte, in, not_in, between, like, not_like, startswith, endswith, isnull"
        ),
    ] = None,
    search: Annotated[str | None, Query(description="Text searched (ILIKE)")] = None,
    search_fields: Annotated[
        str | None, Query(description="Comma separated fields for search, e.g. name,owner.email")
    ] = None,
    sort: Annotated[
        str | None, Query(description="Comma separated, '-' = desc: -created_at,name")
    ] = None,
) -> QuerySpec:
    nodes = parse_filters(filters)
    shorthand: dict[str, list[str]] = {}
    for key, value in request.query_params.multi_items():
        if key not in RESERVED_PARAMS and not key.startswith("_"):
            shorthand.setdefault(key, []).append(value)
    for key, values in shorthand.items():
        nodes.append(Condition(*split_key(key), values if len(values) > 1 else values[0]))
    return QuerySpec(
        filters=nodes, search=search, search_fields=split_csv(search_fields), sort=split_csv(sort)
    )


def pagination_params(
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=settings.PAGE_SIZE_MAX)] = settings.PAGE_SIZE_DEFAULT,
) -> PaginationParams:
    return PaginationParams(page=page, page_size=page_size)


QuerySpecDep = Annotated[QuerySpec, Depends(query_spec)]
PaginationDep = Annotated[PaginationParams, Depends(pagination_params)]


class BaseAPI:
    __abstract__: ClassVar[bool] = True

    # ------------------------------------------------------------- resource
    prefix: ClassVar[str] = ""
    tags: ClassVar[Sequence[str] | None] = None
    service: ClassVar[type[BaseService]]
    response_schema: ClassVar[type[BaseModel]]
    create_schema: ClassVar[type[BaseModel] | None] = None
    update_schema: ClassVar[type[BaseModel] | None] = None
    # Columns/validation of Excel import. Default: create_schema
    import_schema: ClassVar[type[BaseModel] | None] = None
    # Column matching rows to existing records in update/upsert imports (id or a unique column)
    import_key: ClassVar[str] = "id"

    # ------------------------------------------------------------- features
    enable_import: ClassVar[bool] = True
    enable_export: ClassVar[bool] = True
    # Route keys or groups to remove, e.g. ("delete_all", "import")
    disabled_routes: ClassVar[Sequence[str]] = ()

    # ------------------------------------------------- access (whole model)
    public: ClassVar[bool] = False
    auth_required: ClassVar[bool] = True
    roles: ClassVar[Sequence[str] | None] = None
    permission_prefix: ClassVar[str | None] = None
    route_config: ClassVar[Mapping[str, RouteConfig]] = {}

    # ------------------------------------------- limits (0 = no limit, from .env)
    list_limit: ClassVar[int] = settings.LIST_MAX_ROWS
    export_limit: ClassVar[int] = settings.EXPORT_MAX_ROWS
    import_max_rows: ClassVar[int] = settings.IMPORT_MAX_ROWS
    import_max_file_size_mb: ClassVar[int] = settings.IMPORT_MAX_FILE_SIZE_MB

    def __init__(self) -> None:
        cls = type(self)
        if cls.__dict__.get("__abstract__"):
            raise TypeError(f"{cls.__name__} is abstract")
        unknown = (set(cls.disabled_routes) | set(cls.route_config)) - (
            set(ROUTE_GROUPS) | set(ROUTE_GROUPS.values())
        )
        if unknown:
            raise ValueError(f"{cls.__name__}: unknown route keys/groups {unknown}")
        model = cls.service.model
        mapper = sa_inspect(model)
        if cls.import_key not in mapper.column_attrs:
            raise ValueError(f"{cls.__name__}.import_key '{cls.import_key}' is not a column")

        self.model_name = model.__name__
        self.id_type = column_python_type(mapper.columns["id"])
        self.router = APIRouter(prefix=cls.prefix, tags=list(cls.tags or [self.model_name]))
        for key, method, path, _ in ROUTES:
            if self.route_enabled(key):
                endpoint, options = getattr(self, f"_{key}")()
                self.router.add_api_route(
                    path,
                    endpoint,
                    methods=[method],
                    name=f"{self.model_name}.{key}",
                    dependencies=self.route_dependencies(key),
                    **options,
                )

    @classmethod
    def as_router(cls) -> APIRouter:
        return cls().router

    # --------------------------------------------------------------- config
    @property
    def import_model(self) -> type[BaseModel] | None:
        return self.import_schema or self.create_schema

    def route_config_for(self, key: str) -> RouteConfig:
        return (
            self.route_config.get(key) or self.route_config.get(ROUTE_GROUPS[key]) or RouteConfig()
        )

    def route_enabled(self, key: str) -> bool:
        group = ROUTE_GROUPS[key]
        if key in self.disabled_routes or group in self.disabled_routes:
            return False
        if not self.route_config_for(key).enabled:
            return False
        if group == "create":
            return self.create_schema is not None
        if group == "update":
            return self.update_schema is not None
        if group == "import" or key == "export_importable":
            return (
                self.enable_import
                and self.import_model is not None
                and (group == "import" or self.enable_export)
            )
        if group == "export":
            return self.enable_export
        return True

    def route_dependencies(self, key: str) -> list[Any]:
        config = self.route_config_for(key)
        dependencies = [Depends(dependency) for dependency in config.dependencies]
        if self.public:
            return dependencies
        auth = config.auth if config.auth is not None else self.auth_required
        if not auth:
            return dependencies
        roles = config.roles if config.roles is not None else self.roles
        permissions = config.permissions
        if permissions is None and self.permission_prefix:
            permissions = [f"{self.permission_prefix}:{ROUTE_GROUPS[key]}"]
        dependencies.append(Depends(RoleRequired(*roles) if roles else get_current_user))
        if permissions:
            dependencies.append(Depends(PermissionRequired(*permissions)))
        return dependencies

    # -------------------------------------------------------------- helpers
    def _many(self, items: Sequence[Any]) -> list[BaseModel]:
        return [self.response_schema.model_validate(item) for item in items]

    def _check_size(self, count: int) -> None:
        if count > self.list_limit:
            raise CustomException(
                ExceptionType.BAD_REQUEST, f"Too many items: the limit is {self.list_limit}"
            )

    @staticmethod
    def _ensure_selection(spec: QuerySpec, confirm: bool) -> None:
        if not spec.has_selection and not confirm:
            raise CustomException(
                ExceptionType.BAD_REQUEST,
                "No filter/search given: add ?confirm=true to apply to ALL records",
            )

    def _read_upload(self, file: UploadFile) -> BinaryIO:
        """The uploaded file stays on disk (spooled by Starlette): only its size is checked."""
        size = file.size
        if size is None:
            size = file.file.seek(0, 2)
        file.file.seek(0)
        limit_mb = self.import_max_file_size_mb
        if limit_mb and size > limit_mb * 1024 * 1024:
            raise CustomException(http_code=413, message=f"File too large: max {limit_mb} MB")
        if not size:
            raise CustomException(ExceptionType.BAD_REQUEST, "Empty file")
        return file.file

    def _filename(self, suffix: str = "", extension: str = "xlsx") -> str:
        table = self.service.model.__tablename__
        return f"{table}{suffix}_{datetime.now(UTC):%Y%m%d_%H%M%S}.{extension}"

    # ================================================================= read
    def _count(self) -> tuple[Callable, dict]:
        service_cls = self.service

        def count(spec: QuerySpecDep, service: Annotated[service_cls, Depends()]) -> Any:
            return DataResponse(data=service.count(spec))

        return count, {"response_model": DataResponse[int], "summary": f"Count {self.model_name}"}

    def _get_first(self) -> tuple[Callable, dict]:
        service_cls = self.service

        def get_first(spec: QuerySpecDep, service: Annotated[service_cls, Depends()]) -> Any:
            obj = service.get_first(spec)
            if obj is None:
                raise CustomException(ExceptionType.NOT_FOUND, f"{self.model_name} not found")
            return DataResponse(data=self.response_schema.model_validate(obj))

        return get_first, {
            "response_model": DataResponse[self.response_schema],
            "summary": f"First {self.model_name} matching the query",
        }

    def _get_list(self) -> tuple[Callable, dict]:
        service_cls = self.service

        def get_list(spec: QuerySpecDep, service: Annotated[service_cls, Depends()]) -> Any:
            return DataResponse(data=self._many(service.get_list(spec, limit=self.list_limit)))

        return get_list, {
            "response_model": DataResponse[list[self.response_schema]],
            "summary": f"List {self.model_name} (no pagination, max {self.list_limit})",
        }

    def _get_many(self) -> tuple[Callable, dict]:
        service_cls, id_type = self.service, self.id_type

        def get_many(
            ids: Annotated[list[id_type], Query()], service: Annotated[service_cls, Depends()]
        ) -> Any:
            self._check_size(len(ids))
            return DataResponse(data=self._many(service.get_many(ids)))

        return get_many, {
            "response_model": DataResponse[list[self.response_schema]],
            "summary": f"Get {self.model_name} by ids",
        }

    def _get_page(self) -> tuple[Callable, dict]:
        service_cls = self.service

        def get_page(
            spec: QuerySpecDep,
            pagination: PaginationDep,
            service: Annotated[service_cls, Depends()],
        ) -> Any:
            items, metadata = service.get_page(spec, pagination)
            return PageResponse(data=self._many(items), metadata=metadata)

        return get_page, {
            "response_model": PageResponse[self.response_schema],
            "summary": f"Page of {self.model_name}",
        }

    def _get_one(self) -> tuple[Callable, dict]:
        service_cls, id_type = self.service, self.id_type

        def get_one(item_id: id_type, service: Annotated[service_cls, Depends()]) -> Any:
            return DataResponse(
                data=self.response_schema.model_validate(service.get_by_id(item_id))
            )

        return get_one, {
            "response_model": DataResponse[self.response_schema],
            "summary": f"Get {self.model_name}",
        }

    # =============================================================== create
    def _create(self) -> tuple[Callable, dict]:
        service_cls, create_schema = self.service, self.create_schema

        def create(payload: create_schema, service: Annotated[service_cls, Depends()]) -> Any:
            obj = service.create(payload)
            return DataResponse(
                http_code=status.HTTP_201_CREATED, data=self.response_schema.model_validate(obj)
            )

        return create, {
            "status_code": status.HTTP_201_CREATED,
            "response_model": DataResponse[self.response_schema],
            "summary": f"Create {self.model_name}",
        }

    def _create_many(self) -> tuple[Callable, dict]:
        service_cls, create_schema = self.service, self.create_schema

        def create_many(
            payload: Annotated[list[create_schema], Body(min_length=1)],
            service: Annotated[service_cls, Depends()],
        ) -> Any:
            self._check_size(len(payload))
            objects = service.create_many(payload)
            return DataResponse(http_code=status.HTTP_201_CREATED, data=self._many(objects))

        return create_many, {
            "status_code": status.HTTP_201_CREATED,
            "response_model": DataResponse[list[self.response_schema]],
            "summary": f"Create many {self.model_name}",
        }

    # =============================================================== update
    def _update_one(self, partial: bool = False) -> tuple[Callable, dict]:
        service_cls, id_type, update_schema = self.service, self.id_type, self.update_schema

        def update_one(
            item_id: id_type, payload: update_schema, service: Annotated[service_cls, Depends()]
        ) -> Any:
            obj = service.update(service.get_by_id(item_id), payload, partial=partial)
            return DataResponse(data=self.response_schema.model_validate(obj))

        return update_one, {
            "response_model": DataResponse[self.response_schema],
            "summary": f"{'Partially update' if partial else 'Replace'} {self.model_name}",
        }

    def _patch_one(self) -> tuple[Callable, dict]:
        return self._update_one(partial=True)

    def _update_many(self, partial: bool = False) -> tuple[Callable, dict]:
        service_cls = self.service
        item_schema = create_model(
            f"{self.update_schema.__name__}WithId",
            __base__=self.update_schema,
            id=(self.id_type, ...),
        )

        def update_many(
            payload: Annotated[list[item_schema], Body(min_length=1)],
            service: Annotated[service_cls, Depends()],
        ) -> Any:
            self._check_size(len(payload))
            return DataResponse(data=self._many(service.update_many(payload, partial=partial)))

        return update_many, {
            "response_model": DataResponse[list[self.response_schema]],
            "summary": f"{'Partially update' if partial else 'Replace'} many {self.model_name}"
            " (each item has its id)",
        }

    def _patch_many(self) -> tuple[Callable, dict]:
        return self._update_many(partial=True)

    def _update_all(self, partial: bool = False) -> tuple[Callable, dict]:
        service_cls, update_schema = self.service, self.update_schema

        def update_all(
            payload: update_schema,
            spec: QuerySpecDep,
            service: Annotated[service_cls, Depends()],
            confirm: Annotated[bool, Query(description="Required when no filter/search")] = False,
        ) -> Any:
            self._ensure_selection(spec, confirm)
            count = service.update_all(spec, payload, partial=partial)
            return DataResponse(data=BulkResult(count=count))

        return update_all, {
            "response_model": DataResponse[BulkResult],
            "summary": f"{'Partially update' if partial else 'Replace'} every {self.model_name}"
            " matching the query",
        }

    def _patch_all(self) -> tuple[Callable, dict]:
        return self._update_all(partial=True)

    # =============================================================== delete
    def _delete_one(self) -> tuple[Callable, dict]:
        service_cls, id_type = self.service, self.id_type

        def delete_one(item_id: id_type, service: Annotated[service_cls, Depends()]) -> Any:
            service.delete_by_id(item_id)
            return BaseResponse(message=f"{self.model_name} deleted")

        return delete_one, {"response_model": BaseResponse, "summary": f"Delete {self.model_name}"}

    def _delete_many(self) -> tuple[Callable, dict]:
        service_cls, id_type = self.service, self.id_type

        def delete_many(
            ids: Annotated[list[id_type], Query()], service: Annotated[service_cls, Depends()]
        ) -> Any:
            self._check_size(len(ids))
            return DataResponse(data=BulkResult(count=service.delete_many(ids)))

        return delete_many, {
            "response_model": DataResponse[BulkResult],
            "summary": f"Delete {self.model_name} by ids",
        }

    def _delete_all(self) -> tuple[Callable, dict]:
        service_cls = self.service

        def delete_all(
            spec: QuerySpecDep,
            service: Annotated[service_cls, Depends()],
            confirm: Annotated[bool, Query(description="Required when no filter/search")] = False,
        ) -> Any:
            self._ensure_selection(spec, confirm)
            return DataResponse(data=BulkResult(count=service.delete_all(spec)))

        return delete_all, {
            "response_model": DataResponse[BulkResult],
            "summary": f"Delete every {self.model_name} matching the query",
        }

    # =============================================================== export
    def _export(self) -> tuple[Callable, dict]:
        service_cls = self.service

        def export(
            spec: QuerySpecDep,
            service: Annotated[service_cls, Depends()],
            fields: Annotated[
                str | None,
                Query(
                    description="Comma separated columns; relations with dots (owner.email). "
                    "To-many relations are exported as a JSON array. Default: every column"
                ),
            ] = None,
            file_format: Annotated[
                Literal["xlsx", "csv"],
                Query(
                    alias="format",
                    description="xlsx: built on disk then streamed. csv: streamed while rows are "
                    "read (first bytes immediately, best for very large exports)",
                ),
            ] = "xlsx",
        ) -> Response:
            headers, rows = service.export_data(spec, split_csv(fields), limit=self.export_limit)
            if file_format == "csv":
                return csv_streaming_response(headers, rows, self._filename(extension="csv"))
            return xlsx_file_response(headers, rows, self._filename())

        return export, {
            "response_class": Response,
            "responses": _EXPORT_RESPONSE,
            "summary": f"Export {self.model_name} to Excel / CSV",
        }

    def _export_importable(self) -> tuple[Callable, dict]:
        service_cls = self.service

        def export_importable(
            spec: QuerySpecDep, service: Annotated[service_cls, Depends()]
        ) -> Response:
            headers, rows = service.export_importable_data(
                spec, schema=self.import_model, key=self.import_key, limit=self.export_limit
            )
            return xlsx_file_response(headers, rows, self._filename("_import"))

        return export_importable, {
            "response_class": Response,
            "responses": _XLSX_RESPONSE,
            "summary": f"Export {self.model_name} in the import format (edit and re-import)",
        }

    # =============================================================== import
    def _import_template(self) -> tuple[Callable, dict]:
        service_cls = self.service

        def import_template(service: Annotated[service_cls, Depends()]) -> Response:
            content = service.import_template(self.import_model, self.import_key)
            return xlsx_response(content, self._filename("_template"))

        return import_template, {
            "response_class": Response,
            "responses": _XLSX_RESPONSE,
            "summary": f"Download the Excel import template of {self.model_name}",
        }

    def _import(self, dry_run: bool) -> Callable:
        service_cls = self.service

        def run_import(
            file: Annotated[UploadFile, File(description=".xlsx file")],
            service: Annotated[service_cls, Depends()],
            mode: Annotated[ImportMode, Query()] = ImportMode.INSERT,
        ) -> Any:
            result = service.import_excel(
                self._read_upload(file),
                schema=self.import_model,
                mode=mode,
                key=self.import_key,
                dry_run=dry_run,
                max_rows=self.import_max_rows,
            )
            if dry_run:
                return DataResponse(data=result)
            if result.errors:
                rows = len({error.row for error in result.errors})
                raise CustomException(
                    ExceptionType.UNPROCESSABLE_ENTITY,
                    f"Import rejected: {len(result.errors)} errors in {rows} rows",
                    errors=[error.model_dump(mode="json") for error in result.errors],
                )
            return DataResponse(
                data=result,
                message=f"Imported: {result.inserted} inserted, {result.updated} updated",
            )

        return run_import

    def _import_validate(self) -> tuple[Callable, dict]:
        return self._import(dry_run=True), {
            "response_model": DataResponse[ImportResult],
            "summary": f"Validate an Excel import of {self.model_name} (nothing is saved)",
        }

    def _import_data(self) -> tuple[Callable, dict]:
        return self._import(dry_run=False), {
            "response_model": DataResponse[ImportResult],
            "summary": f"Import {self.model_name} from Excel (all rows or nothing)",
        }


class BasePublicAPI(BaseAPI):
    """BaseAPI without any authentication or role check: every route is public."""

    __abstract__ = True
    public = True
    auth_required = False
