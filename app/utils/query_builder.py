"""Dynamic filter / search / sort, defined by the API caller (nothing is fixed in the backend).

Filters - a JSON list in ?filters= (AND-ed). A node is a condition or a group:
    {"field": "price", "op": "gte", "value": 10}
    {"field": "category.name", "op": "in", "value": ["fruit", "veg"]}   # through relationships
    {"or": [{...}, {...}]}   {"and": [...]}   {"not": {...}}
or shorthand query params:  ?price__gte=10&category.name__in=fruit,veg&name=Apple

Operators: eq (default), ne, gt, gte, lt, lte, in, not_in, between, like (contains, case
insensitive), not_like, startswith, endswith, isnull. On ARRAY columns: eq = contains the value,
in = shares any value.

Search: ?search=abc&search_fields=name,owner.email   (fields default to the service search_fields)
Sort:   ?sort=-created_at,name                        ("-" = descending)

Fields listed in a model's __hidden_fields__ can never be filtered, searched, sorted or exported.
"""

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from functools import lru_cache
from typing import Any

from pydantic import TypeAdapter, ValidationError
from sqlalchemy import ColumnElement, String, and_, asc, cast, desc, not_, or_
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import selectinload

from app.utils.exception_handler import CustomException, ExceptionType

OPERATORS = frozenset(
    {
        "eq", "ne", "gt", "gte", "lt", "lte", "in", "not_in", "between",
        "like", "not_like", "startswith", "endswith", "isnull",
    }
)  # fmt: skip
_LIST_OPERATORS = frozenset({"in", "not_in", "between"})
_TEXT_OPERATORS = frozenset({"like", "not_like", "startswith", "endswith"})
MAX_PATH_DEPTH = 4


# ------------------------------------------------------------------- nodes
@dataclass
class Condition:
    field: str
    op: str
    value: Any


@dataclass
class Group:
    kind: str  # "and" | "or"
    items: list["Condition | Group | Not"]


@dataclass
class Not:
    item: "Condition | Group | Not"


FilterNode = Condition | Group | Not


@dataclass
class QuerySpec:
    """Everything a caller can use to select rows."""

    filters: list[FilterNode] = field(default_factory=list)
    search: str | None = None
    search_fields: list[str] | None = None
    sort: list[str] | None = None

    @property
    def has_selection(self) -> bool:
        return bool(self.filters or self.search)


def _bad_request(message: str) -> CustomException:
    return CustomException(ExceptionType.BAD_REQUEST, message)


# ----------------------------------------------------------------- parsing
def split_key(key: str) -> tuple[str, str]:
    """'price__gte' -> ('price', 'gte'); 'name' -> ('name', 'eq')."""
    name, sep, op = key.rpartition("__")
    if sep and op in OPERATORS:
        return name, op
    return key, "eq"


def _parse_node(raw: Any) -> FilterNode:
    if isinstance(raw, Condition | Group | Not):
        return raw
    if not isinstance(raw, Mapping):
        raise _bad_request(f"Invalid filter node: {raw!r}")
    if "field" in raw:
        op = raw.get("op", "eq")
        if op not in OPERATORS:
            raise _bad_request(f"Unknown filter operator '{op}'. Valid: {sorted(OPERATORS)}")
        return Condition(str(raw["field"]), op, raw.get("value"))
    for kind in ("and", "or"):
        if kind in raw:
            items = raw[kind]
            if not isinstance(items, list) or not items:
                raise _bad_request(f"'{kind}' must be a non-empty list")
            return Group(kind, [_parse_node(item) for item in items])
    if "not" in raw:
        return Not(_parse_node(raw["not"]))
    # {"price__gte": 10, "name": "x"}
    return Group("and", [Condition(*split_key(key), value) for key, value in raw.items()])


def parse_filters(raw: Any) -> list[FilterNode]:
    """Accepts None, a JSON string, a dict (node or shorthand mapping) or a list of nodes."""
    if raw is None or raw == "":
        return []
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError as e:
            raise _bad_request(f"filters is not valid JSON: {e.msg}") from e
    if isinstance(raw, Mapping):
        raw = [raw]
    if not isinstance(raw, list):
        raise _bad_request("filters must be a JSON list or object")
    return [_parse_node(item) for item in raw]


def split_csv(value: str | Sequence[str] | None) -> list[str] | None:
    if value is None:
        return None
    if isinstance(value, str):
        value = value.split(",")
    items = [item.strip() for item in value if item and item.strip()]
    return items or None


# --------------------------------------------------------------- resolving
def _hidden(model: type) -> frozenset[str]:
    return frozenset(getattr(model, "__hidden_fields__", ()))


def _check_path(path: str) -> list[str]:
    parts = path.split(".")
    if not path or len(parts) > MAX_PATH_DEPTH or any(not part for part in parts):
        raise _bad_request(f"Invalid field path '{path}'")
    return parts


def column_python_type(column: Any) -> type:
    column_type = column.type.item_type if isinstance(column.type, ARRAY) else column.type
    try:
        return column_type.python_type
    except NotImplementedError:
        return str


@lru_cache(maxsize=256)
def type_adapter(python_type: type) -> TypeAdapter:
    return TypeAdapter(python_type)


def _coerce(python_type: type, value: Any, path: str) -> Any:
    try:
        return type_adapter(python_type).validate_python(value)
    except ValidationError as e:
        if python_type is datetime and isinstance(value, str):
            try:
                return datetime.combine(
                    type_adapter(date).validate_python(value), datetime.min.time()
                )
            except ValidationError:
                pass
        raise _bad_request(f"Invalid value {value!r} for '{path}'") from e


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list | tuple | set):
        return list(value)
    if isinstance(value, str):
        return [item.strip() for item in value.split(",")]
    return [value]


def _as_bool(value: Any, path: str) -> bool:
    return bool(_coerce(bool, value, path))


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _column_condition(column: Any, op: str, value: Any, path: str) -> ColumnElement:
    is_array = isinstance(column.type, ARRAY)
    if op == "isnull":
        return column.is_(None) if _as_bool(value, path) else column.is_not(None)
    if op in _TEXT_OPERATORS:
        text = _escape_like(str(value))
        pattern = {"startswith": f"{text}%", "endswith": f"%{text}"}.get(op, f"%{text}%")
        condition = cast(column, String).ilike(pattern, escape="\\")
        return ~condition if op == "not_like" else condition

    python_type = column_python_type(column)
    if op in _LIST_OPERATORS:
        values = [_coerce(python_type, item, path) for item in _as_list(value)]
        if op == "between":
            if len(values) != 2:
                raise _bad_request(f"'between' on '{path}' needs exactly 2 values")
            return column.between(*values)
        if is_array:
            return column.overlap(values) if op == "in" else ~column.overlap(values)
        return column.in_(values) if op == "in" else column.not_in(values)

    value = _coerce(python_type, value, path)
    if is_array:
        if op == "eq":
            return column.contains([value])
        if op == "ne":
            return ~column.contains([value])
        raise _bad_request(f"Operator '{op}' is not supported on list field '{path}'")
    match op:
        case "eq":
            return column == value
        case "ne":
            return column != value
        case "gt":
            return column > value
        case "gte":
            return column >= value
        case "lt":
            return column < value
        case "lte":
            return column <= value
    raise _bad_request(f"Unknown filter operator '{op}'")


def _path_condition(model: type, parts: list[str], op: str, value: Any, path: str) -> ColumnElement:
    name, rest = parts[0], parts[1:]
    mapper = sa_inspect(model)
    if name in _hidden(model):
        raise _bad_request(f"Field '{path}' is not allowed")
    if name in mapper.relationships:
        relationship = mapper.relationships[name]
        attribute = getattr(model, name)
        if not rest:
            if op != "isnull":
                raise _bad_request(f"'{path}' is a relation: filter on a sub-field, e.g. {path}.id")
            exists = attribute.any() if relationship.uselist else attribute.has()
            return ~exists if _as_bool(value, path) else exists
        inner = _path_condition(relationship.mapper.class_, rest, op, value, path)
        return attribute.any(inner) if relationship.uselist else attribute.has(inner)
    if name in mapper.column_attrs and not rest:
        return _column_condition(getattr(model, name), op, value, path)
    raise _bad_request(f"Unknown field '{path}'")


def build_condition(model: type, node: FilterNode) -> ColumnElement:
    if isinstance(node, Condition):
        return _path_condition(model, _check_path(node.field), node.op, node.value, node.field)
    if isinstance(node, Not):
        return not_(build_condition(model, node.item))
    conditions = [build_condition(model, item) for item in node.items]
    return and_(*conditions) if node.kind == "and" else or_(*conditions)


def build_search(model: type, text: str, fields: Sequence[str]) -> ColumnElement | None:
    text = text.strip()
    if not text or not fields:
        return None
    return or_(*(_path_condition(model, _check_path(path), "like", text, path) for path in fields))


def default_search_fields(model: type) -> list[str]:
    hidden = _hidden(model)
    return [
        column.key
        for column in sa_inspect(model).column_attrs
        if column.key not in hidden
        and isinstance(column.columns[0].type, String)
        and not isinstance(column.columns[0].type, ARRAY)
    ]


def build_order_by(model: type, sort: Sequence[str]) -> list[Any]:
    mapper = sa_inspect(model)
    clauses = []
    for item in sort:
        descending = item.startswith("-")
        name = item.lstrip("+-")
        if name not in mapper.column_attrs or name in _hidden(model):
            raise _bad_request(f"Cannot sort by '{name}'")
        column = getattr(model, name)
        clauses.append(desc(column) if descending else asc(column))
    return clauses


# ------------------------------------------------------------------ export
def visible_columns(model: type) -> list[str]:
    hidden = _hidden(model)
    return [column.key for column in sa_inspect(model).column_attrs if column.key not in hidden]


def validate_field_path(model: type, path: str) -> None:
    """A column, a relation, or a dotted path through relations ending anywhere."""
    current = model
    for part in _check_path(path):
        if current is None:
            raise _bad_request(f"Unknown field '{path}'")
        mapper = sa_inspect(current)
        if part in _hidden(current):
            raise _bad_request(f"Field '{path}' is not allowed")
        if part in mapper.relationships:
            current = mapper.relationships[part].mapper.class_
        elif part in mapper.column_attrs:
            current = None
        else:
            raise _bad_request(f"Unknown field '{path}'")


def loader_options(model: type, paths: Sequence[str]) -> list[Any]:
    """selectinload chains for every relation used by the paths (no N+1 queries)."""
    options = {}
    for path in paths:
        current, loader, chain = model, None, []
        for part in path.split("."):
            relationships = sa_inspect(current).relationships
            if part not in relationships:
                break
            attribute = getattr(current, part)
            loader = selectinload(attribute) if loader is None else loader.selectinload(attribute)
            chain.append(part)
            current = relationships[part].mapper.class_
            options[".".join(chain)] = loader
    # Only the deepest chains are needed
    return [
        opt for key, opt in options.items() if not any(k.startswith(f"{key}.") for k in options)
    ]


def object_to_dict(obj: Any) -> dict[str, Any]:
    model = type(obj)
    return {name: getattr(obj, name) for name in visible_columns(model)}


def get_path_value(obj: Any, path: str) -> tuple[Any, bool]:
    """Value at a dotted path. Returns (value, is_many): through a to-many relation -> list."""
    current, many = [obj], False
    for part in path.split("."):
        next_values = []
        for item in current:
            if item is None:
                continue
            relationships = sa_inspect(type(item)).relationships
            value = getattr(item, part, None)
            if part in relationships and relationships[part].uselist:
                many = True
                next_values.extend(value or [])
            else:
                next_values.append(value)
        current = next_values
    if many:
        return current, True
    return (current[0] if current else None), False
