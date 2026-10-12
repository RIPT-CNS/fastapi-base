"""Generic service: CRUD, bulk operations, dynamic query, Excel import/export.

    class ProductService(BaseService[Product, ProductCreate, ProductUpdate]):
        model = Product
        search_fields = ("name", "sku")     # default fields of ?search= (else every text column)

Use it in an endpoint with `service: Annotated[ProductService, Depends()]`
(the DB session is injected), or outside a request with `ProductService(SessionLocal())`.

Override points:
    get_query()                      base SELECT (joins, eager loads, row-level security)
    before_/after_ create/update/delete
    import_read -> import_transform_row        step 1: receive data
    import_validate -> import_validate_row     step 2: validate (+ import_validate_unique)
    import_save -> import_save_row             step 3: write to the database
    export_fields / export_value               export
    import_export_value                        export in the import format
"""

import json
import types
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from functools import lru_cache
from typing import Annotated, Any, ClassVar, Generic, Literal, TypeVar, Union, get_args, get_origin

from pydantic import BaseModel, ValidationError, create_model
from pydantic.fields import FieldInfo
from sqlalchemy import Select, UniqueConstraint, func, select
from sqlalchemy import inspect as sa_inspect

from app.core.config import settings
from app.core.database import DbSession
from app.models.model_base import BareBaseModel, SoftDeleteMixin
from app.schemas.sche_base import ImportMode, ImportResult, ImportRowError, PaginationParams
from app.schemas.sche_response import MetadataResponse
from app.utils import excel
from app.utils.exception_handler import CustomException, ExceptionType
from app.utils.paging import paginate
from app.utils.query_builder import (
    QuerySpec,
    build_condition,
    build_order_by,
    build_search,
    column_python_type,
    default_search_fields,
    get_path_value,
    loader_options,
    object_to_dict,
    parse_filters,
    type_adapter,
    validate_field_path,
    visible_columns,
)

ModelType = TypeVar("ModelType", bound=BareBaseModel)
CreateSchemaType = TypeVar("CreateSchemaType", bound=BaseModel)
UpdateSchemaType = TypeVar("UpdateSchemaType", bound=BaseModel)

# QuerySpec, or anything parse_filters accepts: {"price__gte": 10}, [{"field": ...}], JSON text
Selection = QuerySpec | Mapping[str, Any] | Sequence[Any] | str | None


# ===================================================================== import
@lru_cache(maxsize=128)
def partial_schema(schema: type[BaseModel]) -> type[BaseModel]:
    """Same fields, constraints and validators, but every field optional (for updates)."""
    fields = {
        name: (
            info.annotation | None,
            FieldInfo.merge_field_infos(info, default=None, default_factory=None),
        )
        for name, info in schema.model_fields.items()
    }
    return create_model(f"{schema.__name__}Partial", __base__=schema, **fields)


@dataclass
class ImportContext:
    mode: ImportMode
    schema: type[BaseModel]
    key: str = "id"
    dry_run: bool = False
    columns: dict[int, str] = field(default_factory=dict)  # sheet column index -> field
    letters: dict[str, str] = field(default_factory=dict)  # field -> column letter
    ignored_columns: list[str] = field(default_factory=list)

    @property
    def partial_schema(self) -> type[BaseModel]:
        return partial_schema(self.schema)

    @property
    def field_names(self) -> list[str]:
        names = list(self.schema.model_fields)
        return names if self.key in names else [self.key, *names]


@dataclass
class ImportRow:
    row: int  # Excel row number
    raw: dict[str, Any]  # field -> cell value (blank cells are absent)
    data: dict[str, Any] = field(default_factory=dict)  # validated values to write
    target: Any = None  # existing record (update) or None (insert)
    errors: list[ImportRowError] = field(default_factory=list)

    def add_error(self, ctx: ImportContext, field_name: str | None, message: str) -> None:
        self.errors.append(
            ImportRowError(
                row=self.row,
                column=ctx.letters.get(field_name) if field_name else None,
                field=field_name,
                message=message,
                value=self.raw.get(field_name) if field_name else None,
            )
        )


def _unwrap(annotation: Any) -> list[Any]:
    """Annotated/Optional/Union -> the concrete types."""
    origin = get_origin(annotation)
    if origin is Annotated:
        return _unwrap(get_args(annotation)[0])
    if origin in (Union, types.UnionType):
        return [t for arg in get_args(annotation) for t in _unwrap(arg) if t is not type(None)]
    return [annotation]


def _type_kinds(annotation: Any) -> set[str]:
    kinds = set()
    for tp in _unwrap(annotation):
        origin = get_origin(tp) or tp
        if origin in (list, set, tuple, frozenset):
            kinds.add("list")
        elif origin is dict:
            kinds.add("dict")
        elif origin is Literal:
            kinds |= {"str" if isinstance(v, str) else "number" for v in get_args(tp)}
        elif isinstance(origin, type):
            if issubclass(origin, Enum):
                kinds |= {"str" if isinstance(m.value, str) else "number" for m in origin}
            elif issubclass(origin, bool):
                kinds.add("bool")
            elif issubclass(origin, int | float | Decimal):
                kinds.add("number")
            elif issubclass(origin, datetime):
                kinds.add("datetime")
            elif issubclass(origin, date):
                kinds.add("date")
            elif issubclass(origin, str):
                kinds.add("str")
            else:
                kinds.add("other")  # EmailStr, HttpUrl, ... (text-like)
    return kinds


def _type_label(annotation: Any) -> str:
    choices = [
        str(value)
        for tp in _unwrap(annotation)
        for value in (
            get_args(tp)
            if get_origin(tp) is Literal
            else [m.value for m in tp]
            if isinstance(tp, type) and issubclass(tp, Enum)
            else []
        )
    ]
    if choices:
        return f"một trong: {', '.join(choices)}"
    kinds = _type_kinds(annotation)
    for kind, label in (
        ("list", "danh sách (JSON hoặc a,b,c)"),
        ("dict", "đối tượng JSON"),
        ("datetime", "ngày giờ (ISO 8601)"),
        ("date", "ngày (YYYY-MM-DD)"),
        ("bool", "true/false"),
        ("number", "số"),
    ):
        if kind in kinds:
            return label
    return "chuỗi"


def coerce_cell(value: Any, annotation: Any) -> Any:
    """Excel cell -> value pydantic can validate for the target type."""
    kinds = _type_kinds(annotation) if annotation is not None else set()
    if isinstance(value, str):
        value = value.strip()
        if kinds & {"list", "dict"} and value[:1] in ("[", "{"):
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                return value
        if "list" in kinds:
            return [item.strip() for item in value.split(",") if item.strip()]
        return value
    if isinstance(value, bool):
        return value
    if (
        isinstance(value, int | float | Decimal)
        and kinds & {"str", "other"}
        and "number" not in kinds
    ):
        if isinstance(value, float) and value.is_integer():
            value = int(value)
        return str(value)
    if isinstance(value, datetime) and "date" in kinds and "datetime" not in kinds:
        return value.date()
    return value


# ==================================================================== service
class BaseService(Generic[ModelType, CreateSchemaType, UpdateSchemaType]):
    model: type[ModelType]
    # Default fields of ?search= when the caller does not send search_fields.
    # Empty -> every text column of the model.
    search_fields: ClassVar[Sequence[str]] = ()
    default_sort: ClassVar[Sequence[str]] = ("-id",)

    def __init__(self, db: DbSession) -> None:
        self.db = db

    @classmethod
    def soft_delete_enabled(cls) -> bool:
        return issubclass(cls.model, SoftDeleteMixin)

    @classmethod
    def column_names(cls) -> tuple[str, ...]:
        return tuple(column.key for column in sa_inspect(cls.model).column_attrs)

    # ================================================================ query
    def get_query(self) -> Select:
        """Base SELECT of every read. Override for joins, eager loads, row-level filters."""
        stmt = select(self.model)
        if self.soft_delete_enabled():
            stmt = stmt.where(self.model.deleted_at.is_(None))
        return stmt

    @staticmethod
    def to_spec(selection: Selection) -> QuerySpec:
        if isinstance(selection, QuerySpec):
            return selection
        return QuerySpec(filters=parse_filters(selection))

    def build_query(self, selection: Selection = None) -> Select:
        """get_query() + filters + search + sort of the selection."""
        spec = self.to_spec(selection)
        stmt = self.get_query()
        for node in spec.filters:
            stmt = stmt.where(build_condition(self.model, node))
        if spec.search:
            fields = spec.search_fields or list(self.search_fields)
            condition = build_search(
                self.model, spec.search, fields or default_search_fields(self.model)
            )
            if condition is not None:
                stmt = stmt.where(condition)
        sort = list(spec.sort or self.default_sort)
        if not any(item.lstrip("+-") == "id" for item in sort):
            sort.append("id")  # stable pagination
        return stmt.order_by(*build_order_by(self.model, sort))

    # ================================================================= read
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

    def get_first(self, selection: Selection = None) -> ModelType | None:
        return self.db.scalar(self.build_query(selection).limit(1))

    def get_many(self, ids: Sequence[Any], *, require_all: bool = False) -> list[ModelType]:
        objects = list(
            self.db.scalars(self.get_query().where(self.model.id.in_(ids)).order_by(self.model.id))
        )
        if require_all and (missing := set(ids) - {obj.id for obj in objects}):
            raise CustomException(
                ExceptionType.NOT_FOUND,
                f"{self.model.__name__} not found: {sorted(missing, key=str)}",
            )
        return objects

    def get_list(self, selection: Selection = None, limit: int | None = None) -> list[ModelType]:
        stmt = self.build_query(selection)
        if limit is not None:
            stmt = stmt.limit(limit)
        return list(self.db.scalars(stmt).unique())

    def get_page(
        self, selection: Selection = None, pagination: PaginationParams | None = None
    ) -> tuple[list[ModelType], MetadataResponse]:
        return paginate(self.db, self.build_query(selection), pagination or PaginationParams())

    def count(self, selection: Selection = None) -> int:
        stmt = self.build_query(selection).order_by(None)
        return self.db.scalar(select(func.count()).select_from(stmt.subquery())) or 0

    # ================================================================ write
    def create(
        self, data: CreateSchemaType | Mapping[str, Any], *, commit: bool = True
    ) -> ModelType:
        values = self.before_create(self._to_dict(data, exclude_unset=False))
        obj = self.model(**values)
        self.db.add(obj)
        self._save(obj, commit)
        self.after_create(obj)
        return obj

    def create_many(
        self, items: Sequence[CreateSchemaType | Mapping[str, Any]], *, commit: bool = True
    ) -> list[ModelType]:
        objects = [self.create(item, commit=False) for item in items]
        if commit:
            self.db.commit()
        return objects

    def update(
        self,
        obj: ModelType,
        data: UpdateSchemaType | Mapping[str, Any],
        *,
        partial: bool = True,
        commit: bool = True,
    ) -> ModelType:
        """partial=True (PATCH): only fields present are written. False (PUT): every field."""
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
        return self.update(self.get_by_id(id), data, partial=False, commit=commit)

    def partial_update_by_id(
        self, id: Any, data: UpdateSchemaType | Mapping[str, Any], *, commit: bool = True
    ) -> ModelType:
        return self.update(self.get_by_id(id), data, partial=True, commit=commit)

    def update_many(
        self,
        items: Sequence[BaseModel | Mapping[str, Any]],
        *,
        partial: bool = True,
        commit: bool = True,
    ) -> list[ModelType]:
        """Each item carries its own "id" and values."""
        rows = [self._to_dict(item, exclude_unset=partial) for item in items]
        ids = [row.pop("id") for row in rows]
        objects = {obj.id: obj for obj in self.get_many(ids, require_all=True)}
        for obj_id, values in zip(ids, rows, strict=True):
            self.update(objects[obj_id], values, partial=partial, commit=False)
        if commit:
            self.db.commit()
        return [objects[obj_id] for obj_id in ids]

    def update_all(
        self,
        selection: Selection,
        data: UpdateSchemaType | Mapping[str, Any],
        *,
        partial: bool = True,
        commit: bool = True,
    ) -> int:
        """Apply the same values to every record matching the selection (hooks run per record)."""
        values = self._to_dict(data, exclude_unset=partial)
        objects = self.get_list(selection)
        for obj in objects:
            self.update(obj, dict(values), partial=partial, commit=False)
        if commit:
            self.db.commit()
        return len(objects)

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

    def delete_many(self, ids: Sequence[Any], *, hard: bool = False, commit: bool = True) -> int:
        objects = self.get_many(ids, require_all=True)
        return self._delete_objects(objects, hard=hard, commit=commit)

    def delete_all(self, selection: Selection, *, hard: bool = False, commit: bool = True) -> int:
        return self._delete_objects(self.get_list(selection), hard=hard, commit=commit)

    # ================================================================ hooks
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

    # =============================================================== export
    def export_fields(self) -> list[str]:
        """Columns exported when the caller does not choose fields."""
        return visible_columns(self.model)

    def export_value(self, obj: ModelType, path: str) -> Any:
        """Value of one cell. Relations: to-one -> value/object, to-many -> list (JSON in Excel)."""
        value, many = get_path_value(obj, path)
        if many:
            return [self._plain(item) for item in value]
        return self._plain(value)

    def export_rows(
        self, selection: Selection, fields: Sequence[str], limit: int | None = None
    ) -> Iterator[list[Any]]:
        # Validate before the workbook starts streaming (errors -> clean 400)
        for path in fields:
            validate_field_path(self.model, path)
        stmt = self.build_query(selection).options(*loader_options(self.model, fields))
        if limit is not None:
            stmt = stmt.limit(limit)
        return ([self.export_value(obj, path) for path in fields] for obj in self.db.scalars(stmt))

    def export_excel(
        self,
        selection: Selection = None,
        fields: Sequence[str] | None = None,
        limit: int | None = settings.EXPORT_MAX_ROWS,
    ) -> bytes:
        fields = list(fields or self.export_fields())
        return excel.build_data_workbook(fields, self.export_rows(selection, fields, limit))

    def export_importable(
        self,
        selection: Selection = None,
        *,
        schema: type[BaseModel],
        key: str = "id",
        limit: int | None = settings.EXPORT_MAX_ROWS,
    ) -> bytes:
        """Same columns as the import template: edit the file and import it back (update/upsert)."""
        fields = ImportContext(ImportMode.UPSERT, schema, key).field_names
        stmt = self.build_query(selection)
        if limit is not None:
            stmt = stmt.limit(limit)
        rows = (
            [self.import_export_value(obj, name) for name in fields]
            for obj in self.db.scalars(stmt)
        )
        return excel.build_data_workbook(fields, rows)

    def import_export_value(self, obj: ModelType, name: str) -> Any:
        """Cell of export_importable. Override for import columns that are not model attributes."""
        if name in sa_inspect(self.model).attrs and name not in self.model.__hidden_fields__:
            return getattr(obj, name)
        return None

    # =============================================================== import
    def import_columns(self, schema: type[BaseModel], key: str = "id") -> list[dict[str, Any]]:
        """Template columns: [{"name", "type", "required", "description"}]."""
        columns = []
        if key not in schema.model_fields:
            columns.append(
                {
                    "name": key,
                    "type": _type_label(column_python_type(getattr(self.model, key))),
                    "required": False,
                    "description": "Khóa để cập nhật (update/upsert). Để trống khi thêm mới.",
                }
            )
        for name, info in schema.model_fields.items():
            columns.append(
                {
                    "name": name,
                    "type": _type_label(info.annotation),
                    "required": info.is_required(),
                    "description": info.description or info.title or "",
                }
            )
        return columns

    def import_template(self, schema: type[BaseModel], key: str = "id") -> bytes:
        return excel.build_template_workbook(self.import_columns(schema, key))

    def import_excel(
        self,
        content: bytes,
        *,
        schema: type[BaseModel],
        mode: ImportMode = ImportMode.INSERT,
        key: str = "id",
        dry_run: bool = False,
        max_rows: int = settings.IMPORT_MAX_ROWS,
    ) -> ImportResult:
        """Receive -> validate -> save. Nothing is written if any row is invalid."""
        ctx = ImportContext(mode=mode, schema=schema, key=key, dry_run=dry_run)
        rows = self.import_read(content, ctx, max_rows)
        self.import_validate(rows, ctx)
        result = ImportResult(
            mode=mode,
            dry_run=dry_run,
            total_rows=len(rows),
            valid_rows=sum(1 for row in rows if not row.errors),
            ignored_columns=ctx.ignored_columns,
            errors=[error for row in rows for error in row.errors],
        )
        if result.errors or dry_run:
            return result
        return self.import_save(rows, ctx, result)

    # ----------------------------------------------------- step 1: receive
    def import_read(self, content: bytes, ctx: ImportContext, max_rows: int) -> list[ImportRow]:
        """Parse the sheet, map headers to fields (name, alias or title), transform each row."""
        header, data = excel.read_data_sheet(content, max_rows)
        lookup = {}
        for name in ctx.field_names:
            lookup[name.lower()] = name
            info = ctx.schema.model_fields.get(name)
            for label in (info.alias, info.title) if info else ():
                if label:
                    lookup[label.lower()] = name
        for index, cell in enumerate(header):
            if excel.is_blank(cell):
                continue
            name = lookup.get(str(cell).strip().rstrip("*").strip().lower())
            if name is None or name in ctx.letters:
                ctx.ignored_columns.append(str(cell))
                continue
            ctx.columns[index] = name
            ctx.letters[name] = excel.column_letter(index)

        rows = []
        for row_number, cells in data:
            raw = {
                name: cells[index]
                for index, name in ctx.columns.items()
                if index < len(cells) and not excel.is_blank(cells[index])
            }
            rows.append(ImportRow(row=row_number, raw=self.import_transform_row(raw, ctx)))
        return rows

    def import_transform_row(self, values: dict[str, Any], ctx: ImportContext) -> dict[str, Any]:
        """Convert raw cells (numbers in text fields, JSON lists, dates). Override to clean."""
        annotations = {name: info.annotation for name, info in ctx.schema.model_fields.items()}
        if ctx.key not in annotations:
            annotations[ctx.key] = column_python_type(getattr(self.model, ctx.key))
        return {name: coerce_cell(value, annotations.get(name)) for name, value in values.items()}

    # ---------------------------------------------------- step 2: validate
    def import_validate(self, rows: list[ImportRow], ctx: ImportContext) -> None:
        """Find target records, validate each row with the schema, then cross-row checks."""
        targets = self._import_targets(rows, ctx)
        key_in_schema = ctx.key in ctx.schema.model_fields
        for row in rows:
            if row.errors:
                continue
            key_value = row.raw.get(ctx.key)
            target = targets.get(row.row)
            if ctx.mode == ImportMode.UPDATE and target is None:
                row.add_error(
                    ctx, ctx.key, "Required in update mode" if key_value is None else "Not found"
                )
                continue
            if (
                ctx.mode == ImportMode.UPSERT
                and target is None
                and key_value is not None
                and not key_in_schema
            ):
                row.add_error(ctx, ctx.key, "Not found")
                continue
            row.target = target

            schema = ctx.schema if target is None else ctx.partial_schema
            payload = {
                name: value for name, value in row.raw.items() if name in schema.model_fields
            }
            try:
                validated = schema.model_validate(payload)
            except ValidationError as e:
                for error in e.errors():
                    name = str(error["loc"][0]) if error["loc"] else None
                    row.add_error(ctx, name, error["msg"])
                continue
            row.data = validated.model_dump(exclude_unset=target is not None)
            for name, message in (self.import_validate_row(row, ctx) or {}).items():
                row.add_error(ctx, name, message)
        self.import_validate_unique(rows, ctx)

    def import_validate_row(self, row: ImportRow, ctx: ImportContext) -> dict[str | None, str]:
        """Custom business rules for one row: return {field: error message}.
        row.data = validated values, row.target = existing record (None when inserting)."""
        return {}

    def import_validate_unique(self, rows: list[ImportRow], ctx: ImportContext) -> None:
        """Unique columns: no duplicate inside the file, no clash with other records in the DB."""
        for name in self._unique_columns():
            owners: dict[Any, list[ImportRow]] = {}
            for row in rows:
                if not row.errors and row.data.get(name) is not None:
                    owners.setdefault(row.data[name], []).append(row)
            if not owners:
                continue
            for duplicated in (group for group in owners.values() if len(group) > 1):
                numbers = ", ".join(str(row.row) for row in duplicated)
                for row in duplicated:
                    row.add_error(ctx, name, f"Duplicate value in file (rows {numbers})")
            column = getattr(self.model, name)
            existing = dict(
                self.db.execute(select(column, self.model.id).where(column.in_(list(owners)))).all()
            )
            for value, group in owners.items():
                if value in existing and len(group) == 1:
                    row = group[0]
                    if row.target is None or row.target.id != existing[value]:
                        row.add_error(ctx, name, "Value already exists")

    # -------------------------------------------------------- step 3: save
    def import_save(
        self, rows: list[ImportRow], ctx: ImportContext, result: ImportResult
    ) -> ImportResult:
        """Write every row in one transaction."""
        for row in rows:
            if self.import_save_row(row, ctx) == "inserted":
                result.inserted += 1
            else:
                result.updated += 1
        self.db.commit()
        return result

    def import_save_row(self, row: ImportRow, ctx: ImportContext) -> Literal["inserted", "updated"]:
        if row.target is None:
            self.create(row.data, commit=False)
            return "inserted"
        self.update(row.target, row.data, partial=True, commit=False)
        return "updated"

    # ============================================================ internals
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

    def _delete_objects(self, objects: Sequence[ModelType], *, hard: bool, commit: bool) -> int:
        for obj in objects:
            self.delete(obj, hard=hard, commit=False)
        if commit:
            self.db.commit()
        return len(objects)

    @staticmethod
    def _plain(value: Any) -> Any:
        if isinstance(value, BareBaseModel):
            return object_to_dict(value)
        return value

    def _unique_columns(self) -> list[str]:
        table = self.model.__table__
        columns = {column for column in table.columns if column.unique}
        columns |= {
            next(iter(index.columns))
            for index in table.indexes
            if index.unique and len(index.columns) == 1
        }
        columns |= {
            next(iter(constraint.columns))
            for constraint in table.constraints
            if isinstance(constraint, UniqueConstraint) and len(constraint.columns) == 1
        }
        mapper = sa_inspect(self.model)
        return sorted(
            mapper.get_property_by_column(column).key
            for column in columns
            if not column.primary_key
        )

    def _import_targets(self, rows: list[ImportRow], ctx: ImportContext) -> dict[int, ModelType]:
        """Excel row number -> existing record matched by the import key."""
        if ctx.mode == ImportMode.INSERT:
            return {}
        column = getattr(self.model, ctx.key)
        adapter = type_adapter(column_python_type(column))
        keys: dict[int, Any] = {}
        for row in rows:
            value = row.raw.get(ctx.key)
            if value is None:
                continue
            try:
                keys[row.row] = adapter.validate_python(value)
            except ValidationError:
                row.add_error(ctx, ctx.key, "Invalid value")
        if not keys:
            return {}
        found = {
            getattr(obj, ctx.key): obj
            for obj in self.db.scalars(self.get_query().where(column.in_(set(keys.values()))))
        }
        return {number: found[value] for number, value in keys.items() if value in found}
