"""Generic CRUD service. A new resource only needs:

    class ProductService(BaseService[Product, ProductCreate, ProductUpdate]):
        model = Product
        search_fields = ("name", "sku")                          # ?search=
        filter_fields = {"category_id": ("eq", "in"), "price": ("gte", "lte")}
        sort_fields = ("id", "name", "price", "created_at")      # ?sort_by=

Use it in an endpoint with `service: Annotated[ProductService, Depends()]`
(the DB session is injected), or outside a request with `ProductService(SessionLocal())`.
Override `get_query()` for row-level scoping and the before_/after_ hooks for business rules.
"""

from collections.abc import Mapping, Sequence
from typing import Any, ClassVar, Generic, Literal, TypeVar

from pydantic import BaseModel
from sqlalchemy import Select, String, asc, cast, desc, func, or_, select
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm.attributes import InstrumentedAttribute

from app.core.database import DbSession
from app.models.model_base import BareBaseModel, SoftDeleteMixin
from app.schemas.sche_base import PaginationParams, SortParams
from app.schemas.sche_response import MetadataResponse
from app.utils.exception_handler import CustomException, ExceptionType
from app.utils.paging import paginate

ModelType = TypeVar("ModelType", bound=BareBaseModel)
CreateSchemaType = TypeVar("CreateSchemaType", bound=BaseModel)
UpdateSchemaType = TypeVar("UpdateSchemaType", bound=BaseModel)

FILTER_OPERATORS = frozenset(
    {"eq", "ne", "gt", "gte", "lt", "lte", "in", "not_in", "like", "isnull"}
)


class BaseService(Generic[ModelType, CreateSchemaType, UpdateSchemaType]):
    model: type[ModelType]
    # Columns searched (ILIKE, OR-ed) by ?search=
    search_fields: ClassVar[Sequence[str]] = ()
    # ("status", "owner_id") -> equality only; {"price": ("gte", "lte")} -> chosen operators.
    # Query param name: "<field>" for eq, "<field>__<op>" otherwise.
    filter_fields: ClassVar[Sequence[str] | Mapping[str, Sequence[str]]] = ()
    # Allowed ?sort_by= values. Empty -> every column
    sort_fields: ClassVar[Sequence[str]] = ()
    default_sort_by: ClassVar[str] = "id"
    default_order: ClassVar[Literal["asc", "desc"]] = "desc"

    def __init__(self, db: DbSession) -> None:
        self.db = db

    # ------------------------------------------------------------ class info
    @classmethod
    def soft_delete_enabled(cls) -> bool:
        return issubclass(cls.model, SoftDeleteMixin)

    @classmethod
    def column_names(cls) -> tuple[str, ...]:
        return tuple(column.key for column in sa_inspect(cls.model).column_attrs)

    @classmethod
    def get_sort_fields(cls) -> tuple[str, ...]:
        return tuple(cls.sort_fields) or cls.column_names()

    @classmethod
    def get_filter_fields(cls) -> dict[str, tuple[str, ...]]:
        if isinstance(cls.filter_fields, Mapping):
            fields = {name: tuple(ops) for name, ops in cls.filter_fields.items()}
        else:
            fields = {name: ("eq",) for name in cls.filter_fields}
        columns = set(cls.column_names())
        for name, ops in fields.items():
            if name not in columns:
                raise ValueError(f"{cls.__name__}.filter_fields: unknown column '{name}'")
            if unknown := set(ops) - FILTER_OPERATORS:
                raise ValueError(f"{cls.__name__}.filter_fields: unknown operators {unknown}")
        return fields

    # ------------------------------------------------------------------ query
    def get_query(self) -> Select:
        """Base SELECT used by every read. Override to add joins/eager loads/row-level filters."""
        stmt = select(self.model)
        if self.soft_delete_enabled():
            stmt = stmt.where(self.model.deleted_at.is_(None))
        return stmt

    # ------------------------------------------------------------------- read
    def get_by_id_optional(self, id: Any) -> ModelType | None:
        return self.db.scalar(self.get_query().where(self.model.id == id))

    def get_by_id(self, id: Any) -> ModelType:
        obj = self.get_by_id_optional(id)
        if obj is None:
            raise CustomException(ExceptionType.NOT_FOUND, f"{self.model.__name__} not found")
        return obj

    def get_one_by(self, **conditions: Any) -> ModelType | None:
        return self.db.scalar(self.get_query().filter_by(**conditions).limit(1))

    def exists(self, **conditions: Any) -> bool:
        return self.get_one_by(**conditions) is not None

    def count(self, filters: Mapping[str, Any] | None = None) -> int:
        stmt = self._apply_filters(self.get_query(), filters)
        return self.db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery())) or 0

    def get_all(
        self,
        sort_params: SortParams | None = None,
        filters: Mapping[str, Any] | None = None,
        search: str | None = None,
    ) -> list[ModelType]:
        """Every matching row, unpaginated. Prefer get_by_filter for API endpoints."""
        stmt = self._build_list_query(sort_params, filters, search)
        return list(self.db.scalars(stmt).unique().all())

    def get_by_filter(
        self,
        pagination_params: PaginationParams | None = None,
        sort_params: SortParams | None = None,
        filters: Mapping[str, Any] | None = None,
        search: str | None = None,
    ) -> tuple[list[ModelType], MetadataResponse]:
        stmt = self._build_list_query(sort_params, filters, search)
        return paginate(self.db, stmt, pagination_params or PaginationParams())

    # ------------------------------------------------------------------ write
    def create(
        self, data: CreateSchemaType | Mapping[str, Any], *, commit: bool = True
    ) -> ModelType:
        values = self.before_create(self._to_dict(data, exclude_unset=False))
        obj = self.model(**values)
        self.db.add(obj)
        self._save(obj, commit)
        self.after_create(obj)
        return obj

    def update(
        self,
        obj: ModelType,
        data: UpdateSchemaType | Mapping[str, Any],
        *,
        partial: bool = True,
        commit: bool = True,
    ) -> ModelType:
        values = self.before_update(obj, self._to_dict(data, exclude_unset=partial))
        attributes = sa_inspect(self.model).attrs
        for key, value in values.items():
            if key not in attributes:
                raise ValueError(f"{self.model.__name__} has no attribute '{key}'")
            setattr(obj, key, value)
        self._save(obj, commit)
        self.after_update(obj)
        return obj

    def update_by_id(
        self, id: Any, data: UpdateSchemaType | Mapping[str, Any], *, commit: bool = True
    ) -> ModelType:
        """Full update (PUT): every field of the schema is written, unset ones get their default."""
        return self.update(self.get_by_id(id), data, partial=False, commit=commit)

    def partial_update_by_id(
        self, id: Any, data: UpdateSchemaType | Mapping[str, Any], *, commit: bool = True
    ) -> ModelType:
        """Partial update (PATCH): only fields present in the request are written."""
        return self.update(self.get_by_id(id), data, partial=True, commit=commit)

    def delete(self, obj: ModelType, *, hard: bool = False, commit: bool = True) -> None:
        """Soft delete if the model has SoftDeleteMixin (unless hard=True), otherwise DELETE."""
        self.before_delete(obj)
        if self.soft_delete_enabled() and not hard:
            obj.deleted_at = func.now()
            self._save(obj, commit)
        else:
            self.db.delete(obj)
            self.db.flush()
            if commit:
                self.db.commit()
        self.after_delete(obj)

    def delete_by_id(self, id: Any, *, hard: bool = False, commit: bool = True) -> None:
        self.delete(self.get_by_id(id), hard=hard, commit=commit)

    # ------------------------------------------------------------------ hooks
    def before_create(self, data: dict[str, Any]) -> dict[str, Any]:
        return data

    def after_create(self, obj: ModelType) -> None:
        pass

    def before_update(self, obj: ModelType, data: dict[str, Any]) -> dict[str, Any]:
        return data

    def after_update(self, obj: ModelType) -> None:
        pass

    def before_delete(self, obj: ModelType) -> None:
        pass

    def after_delete(self, obj: ModelType) -> None:
        pass

    # -------------------------------------------------------------- internals
    @staticmethod
    def _to_dict(data: BaseModel | Mapping[str, Any], *, exclude_unset: bool) -> dict[str, Any]:
        if isinstance(data, BaseModel):
            return data.model_dump(exclude_unset=exclude_unset)
        return dict(data)

    def _save(self, obj: ModelType, commit: bool) -> None:
        self.db.flush()
        if commit:
            self.db.commit()
        # Load server-generated values (id, created_at, updated_at, ...)
        self.db.refresh(obj)

    def _column(self, name: str) -> InstrumentedAttribute:
        if name not in self.column_names():
            raise CustomException(ExceptionType.BAD_REQUEST, f"Unknown field '{name}'")
        return getattr(self.model, name)

    def _build_list_query(
        self,
        sort_params: SortParams | None,
        filters: Mapping[str, Any] | None,
        search: str | None,
    ) -> Select:
        stmt = self._apply_filters(self.get_query(), filters)
        stmt = self._apply_search(stmt, search)
        return self._apply_sort(stmt, sort_params)

    def _apply_filters(self, stmt: Select, filters: Mapping[str, Any] | None) -> Select:
        for key, value in (filters or {}).items():
            if value is None:
                continue
            name, _, op = key.partition("__")
            stmt = stmt.where(self._condition(self._column(name), op or "eq", value))
        return stmt

    @staticmethod
    def _condition(column: InstrumentedAttribute, op: str, value: Any) -> Any:
        is_array = isinstance(column.type, ARRAY)
        values = list(value) if isinstance(value, (list, tuple, set)) else [value]
        match op:
            case "eq":
                return column.contains([value]) if is_array else column == value
            case "ne":
                return ~column.contains([value]) if is_array else column != value
            case "gt":
                return column > value
            case "gte":
                return column >= value
            case "lt":
                return column < value
            case "lte":
                return column <= value
            case "in":
                return column.overlap(values) if is_array else column.in_(values)
            case "not_in":
                return ~column.overlap(values) if is_array else column.not_in(values)
            case "like":
                escaped = str(value).replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
                return cast(column, String).ilike(f"%{escaped}%", escape="\\")
            case "isnull":
                return column.is_(None) if value else column.is_not(None)
        raise CustomException(ExceptionType.BAD_REQUEST, f"Unsupported filter operator '{op}'")

    def _apply_search(self, stmt: Select, search: str | None) -> Select:
        if not search or not self.search_fields:
            return stmt
        escaped = search.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        pattern = f"%{escaped}%"
        return stmt.where(
            or_(
                *(
                    cast(getattr(self.model, field), String).ilike(pattern, escape="\\")
                    for field in self.search_fields
                )
            )
        )

    def _apply_sort(self, stmt: Select, sort_params: SortParams | None) -> Select:
        sort_by = (sort_params.sort_by if sort_params else None) or self.default_sort_by
        order = (sort_params.order if sort_params else None) or self.default_order
        if sort_by not in self.get_sort_fields():
            raise CustomException(ExceptionType.BAD_REQUEST, f"Cannot sort by '{sort_by}'")
        direction = desc if order == "desc" else asc
        stmt = stmt.order_by(direction(getattr(self.model, sort_by)))
        if sort_by != "id":
            # Stable ordering across pages
            stmt = stmt.order_by(direction(self.model.id))
        return stmt
