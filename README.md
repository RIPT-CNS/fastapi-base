# FASTAPI_BASE

Backend base: **FastAPI + PostgreSQL + SQLAlchemy 2 + Alembic + Keycloak**, chạy hoàn toàn bằng Docker.

- **Một lệnh là chạy đủ**: PostgreSQL, migration, tạo admin, API (hot reload). Keycloak dùng server có sẵn bên ngoài.
- **Gọn**: 1 `Dockerfile`, 1 `docker-compose.yml`, 1 `requirements.txt`. Dev hay prod chỉ khác nhau ở `.env`.
- **Xác thực**: JWT local (access + refresh, thu hồi token), HTTP Basic, SSO Keycloak (verify JWT offline qua JWKS, tự tạo user lần đầu đăng nhập).
- **Phân quyền**: theo role (local + role từ Keycloak) và theo permission (`resource:action`, có wildcard).
- **BaseAPI**: khai báo 1 class là có 22 API: CRUD, bulk (many/all), phân trang, **filter/search/sort động do client tự định nghĩa**, soft delete, **import/export Excel** (validate lỗi từng dòng/cột, insert/update/upsert). Bật/tắt và phân quyền theo từng API hoặc cả model; có `BasePublicAPI`.
- Response thống nhất, xử lý lỗi tập trung, request-id trong log, test với PostgreSQL thật.

## Khởi động nhanh

```bash
cp .env.example .env      # hoặc: make env
docker compose up -d --build   # hoặc: make up
```

| Dịch vụ | URL | Tài khoản |
| --- | --- | --- |
| Swagger UI | http://localhost:8000/docs | |
| API | http://localhost:8000/api | admin / `Admin@123` (local) |
| PostgreSQL | localhost:5432 | postgres / postgres |

Cổng host đổi trong `.env`: `APP_PORT`, `DB_PORT`. Trỏ tới Keycloak của bạn bằng các biến `KEYCLOAK_*` (xem [Keycloak SSO](#keycloak-sso)); không dùng SSO thì đặt `KEYCLOAK_ENABLED=false`.

Thứ tự khởi động: `db` (healthy) → `migrate` (`alembic upgrade head` + tạo admin, rồi thoát) → `app`. App không gọi Keycloak lúc khởi động.

Trong Swagger, nút **Authorize** có 4 cách: `LocalLogin` (username/password), `KeycloakSSO` (đăng nhập qua trang Keycloak), `BearerToken` (dán token), `BasicAuth`.

`make help` liệt kê mọi lệnh: `up`, `down`, `logs`, `migrate`, `migration m="..."`, `test`, `lint`, `format`, `shell`, `psql`, `clean`.

## Cấu trúc

```txt
.
├── app
│   ├── api
│   │   ├── api_auth.py         # /auth: login, token, refresh, register, me, change-password, logout
│   │   ├── api_auth_sso.py     # /auth/sso: Keycloak (chỉ bật khi KEYCLOAK_ENABLED=true)
│   │   ├── api_healthcheck.py  # /health-check, /health-check/ready
│   │   └── v1/api_user.py      # UserAPI(BaseAPI) (tự động mount ở /api/v1/users)
│   ├── core
│   │   ├── config.py           # Settings (đọc env / .env), validate cấu hình prod
│   │   ├── database.py         # engine, get_db, DbSession
│   │   ├── security.py         # hash password (argon2/bcrypt), JWT local
│   │   ├── keycloak.py         # OIDC client: verify JWT qua JWKS, token/refresh/logout
│   │   ├── permissions.py      # map role -> permission
│   │   ├── base_api.py         # BaseAPI / BasePublicAPI / RouteConfig
│   │   ├── router.py           # tự động include app/api/v*/api_*.py
│   │   ├── logging.py, middleware.py
│   ├── models                  # model_*.py được import tự động (Alembic thấy ngay)
│   ├── schemas                 # sche_*.py: Pydantic request/response
│   ├── services                # srv_base.py (BaseService), srv_user.py, srv_auth.py
│   ├── utils                   # login_manager.py (auth), query_builder.py (query động), excel.py, ...
│   ├── cli.py                  # python -m app.cli serve | migrate | seed | create-user
│   └── main.py
├── alembic/versions            # migration
├── tests
├── .env.example                # MỌI cấu hình dev/prod
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
└── Makefile
```

## Dev và Prod

Cùng một `Dockerfile`, `docker-compose.yml`, `requirements.txt`; chỉ khác `.env`. Lệnh chạy luôn là `docker compose up -d --build` (`make up`).

| Biến trong `.env` | Dev | Prod |
| --- | --- | --- |
| `ENVIRONMENT` | `dev`: hot reload, 1 process | `prod`: `WEB_CONCURRENCY` worker, kiểm tra cấu hình khi khởi động |
| `DEBUG` / `LOG_JSON` | `true` / `false` | `false` / `true` |
| `KEYCLOAK_SERVER_URL` / `KEYCLOAK_PUBLIC_URL` | Keycloak dev/test | `https://sso.example.com` |
| `DB_BIND` | `127.0.0.1` | `127.0.0.1` (DB không lộ ra ngoài) |

Các dòng cần đổi khi lên prod được đánh dấu `[PROD]` trong `.env.example`. Khi `ENVIRONMENT=prod`, app **từ chối khởi động** nếu `SECRET_KEY` ngắn hơn 32 ký tự hoặc chứa `change-me`, hoặc `DEBUG=true`. Tối thiểu:

```env
ENVIRONMENT=prod
DEBUG=false
LOG_JSON=true
SECRET_KEY=<openssl rand -hex 32>
POSTGRES_PASSWORD=<mạnh>
FIRST_SUPERUSER_PASSWORD=<mạnh>     # hoặc để trống để không tạo admin
BACKEND_CORS_ORIGINS=https://app.example.com
KEYCLOAK_SERVER_URL=https://sso.example.com
KEYCLOAK_PUBLIC_URL=https://sso.example.com
KEYCLOAK_CLIENT_SECRET=<secret của client>
```

Code được mount vào container (`.:/app`) ở mọi môi trường: cập nhật prod bằng `git pull && docker compose up -d --build` (chạy lại migrate + restart app). Muốn image bất biến (đẩy lên registry) thì bỏ dòng `volumes: - .:/app` trong `docker-compose.yml`.

Đặt reverse proxy (nginx/traefik) có TLS phía trước app; uvicorn đã bật proxy headers.

Chạy không dùng Docker: `pip install -r requirements.txt`, trong `.env` sửa `POSTGRES_HOST=localhost`, `POSTGRES_PORT=<DB_PORT>`, `KEYCLOAK_SERVER_URL` trỏ thẳng tới Keycloak, rồi `python -m app.cli migrate && python -m app.cli serve`.

## Thêm một module mới

Ví dụ resource `Product`. Chỉ cần 4 file + 1 migration, **không phải đăng ký ở đâu khác**.

**1. Model** — `app/models/model_product.py`

```python
from decimal import Decimal

from sqlalchemy import ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.model_base import BareBaseModel, SoftDeleteMixin


class Product(SoftDeleteMixin, BareBaseModel):   # bỏ SoftDeleteMixin nếu muốn xoá cứng
    __tablename__ = "products"                    # mặc định: tên class dạng snake_case

    name: Mapped[str] = mapped_column(String(255), index=True)
    sku: Mapped[str] = mapped_column(String(50), unique=True)
    price: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    category: Mapped[str | None] = mapped_column(String(50), index=True)
    owner_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
```

`BareBaseModel` đã có `id`, `created_at`, `updated_at`.

**2. Schemas** — `app/schemas/sche_product.py`

```python
from decimal import Decimal

from app.schemas.sche_base import BaseModelResponse, BaseSchema


class ProductCreateRequest(BaseSchema):
    name: str
    sku: str
    price: Decimal = Decimal(0)
    category: str | None = None


class ProductUpdateRequest(BaseSchema):
    name: str | None = None
    price: Decimal | None = None
    category: str | None = None


class ProductResponse(BaseModelResponse):
    name: str
    sku: str
    price: Decimal
    category: str | None
```

**3. Service** — `app/services/srv_product.py`

```python
from app.models.model_product import Product
from app.schemas.sche_product import ProductCreateRequest, ProductUpdateRequest
from app.services.srv_base import BaseService


class ProductService(BaseService[Product, ProductCreateRequest, ProductUpdateRequest]):
    model = Product
    search_fields = ("name", "sku")   # field mặc định của ?search= (bỏ trống = mọi cột text)
```

**4. API** — `app/api/v1/api_product.py` (mọi class `BaseAPI` trong file `api_*.py` ở `app/api/vN/` được mount tự động)

```python
from app.core.base_api import BaseAPI, RouteConfig
from app.schemas.sche_product import ProductCreateRequest, ProductResponse, ProductUpdateRequest
from app.services.srv_product import ProductService
from app.utils.enums import RouteGroup


class ProductAPI(BaseAPI):
    prefix = "/products"
    tags = ["Products"]
    service = ProductService
    response_schema = ProductResponse
    create_schema = ProductCreateRequest
    update_schema = ProductUpdateRequest
    permission_prefix = "product"                       # product:read / create / update / ...
    route_config = {RouteGroup.READ: RouteConfig(auth=False)}   # các API đọc: public
```

**5. Migration**

```bash
make migration m="add products"   # tạo file trong alembic/versions — đọc lại trước khi commit
make migrate
```

Kết quả: 22 API ở `/api/v1/products` (và alias `/api/products` vì `API_VERSION=v1`), gồm CRUD, bulk, import/export Excel.

### BaseAPI — danh sách API

| Key | Method + path | Nhóm |
| --- | --- | --- |
| `get_page` | `GET /products` (phân trang) | read |
| `get_list` | `GET /products/list` (không phân trang, tối đa `LIST_MAX_ROWS`) | read |
| `get_many` | `GET /products/many?ids=1&ids=2` | read |
| `get_first` | `GET /products/first` (bản ghi đầu tiên khớp query) | read |
| `get_one` | `GET /products/{id}` | read |
| `count` | `GET /products/count` | read |
| `create_one` / `create_many` | `POST /products` / `POST /products/many` (body: list) | create |
| `update_one` / `patch_one` | `PUT` / `PATCH /products/{id}` | update |
| `update_many` / `patch_many` | `PUT` / `PATCH /products/many` (body: `[{"id": 1, ...}, ...]`) | update |
| `update_all` / `patch_all` | `PUT` / `PATCH /products/all?<filter>` (cùng giá trị cho mọi bản ghi khớp) | update |
| `delete_one` / `delete_many` / `delete_all` | `DELETE /products/{id}` / `/many?ids=` / `/all?<filter>` | delete |
| `import_template` | `GET /products/import/template` | import |
| `import_validate` | `POST /products/import/validate?mode=` (chỉ kiểm tra, không ghi) | import |
| `import_data` | `POST /products/import?mode=insert\|update\|upsert` | import |
| `export_data` | `GET /products/export?fields=&format=xlsx\|csv` | export |
| `export_importable` | `GET /products/export/importable` (định dạng nhập lại được) | export |

- `PUT` ghi **toàn bộ** field của `update_schema` (field không gửi về giá trị mặc định); `PATCH` chỉ ghi field có gửi.
- `/all` (update/delete) từ chối chạy nếu không có filter/search, trừ khi thêm `?confirm=true`.
- Mọi thao tác ghi chạy hook của service từng bản ghi (hash password, soft delete, ...) và nằm trong 1 transaction.

### Query động (filter, search, sort)

Client tự chọn field, toán tử, giá trị khi gọi API; backend không cần khai báo trước. Áp dụng cho mọi API đọc, `/all` và export.

```text
# Viết tắt: field__op=value (nhiều điều kiện = AND)
GET /products?price__gte=10&price__lt=100&category.name__in=fruit,veg&name__like=táo

# JSON, có or / and / not, lồng nhau tuỳ ý
GET /products?filters=[{"or":[{"field":"price","op":"gte","value":100},
                              {"field":"owner.email","op":"endswith","value":"@ptit.edu.vn"}]},
                       {"not":{"field":"tags","value":"hidden"}}]

GET /products?search=bút&search_fields=name,sku,category.name     # ILIKE, OR giữa các field
GET /products?sort=-price,name                                     # "-" = giảm dần
```

| Toán tử | Ý nghĩa |
| --- | --- |
| `eq` (mặc định), `ne`, `gt`, `gte`, `lt`, `lte` | so sánh |
| `in`, `not_in` | danh sách: `a,b,c` hoặc lặp lại tham số |
| `between` | `?price__between=10,20` |
| `like`, `not_like`, `startswith`, `endswith` | không phân biệt hoa thường, ký tự `%` `_` được escape |
| `isnull` | `?deleted_at__isnull=true`; trên quan hệ: `?category__isnull=true` |

- Field đi qua quan hệ bằng dấu chấm (`owner.email`, `items.name`, tối đa 4 cấp): quan hệ 1 dùng `has`, quan hệ nhiều dùng `any`.
- Cột ARRAY: `eq` = có chứa phần tử, `in` = có chung ít nhất 1 phần tử.
- Giá trị tự ép kiểu theo cột (`"10"` → số, `"2024-01-31"` → ngày); sai kiểu, field không tồn tại hoặc toán tử lạ → 400.
- Cột liệt kê trong `__hidden_fields__` của model (vd. `User.hashed_password`) **không bao giờ** lọc/tìm/sắp xếp/export được.
- Tên tham số dành riêng (không dùng làm filter viết tắt được, hãy dùng `filters=`): `filters search search_fields sort page page_size ids fields confirm mode`.

### BaseAPI — cấu hình

| Thuộc tính class | Mặc định | Ý nghĩa |
| --- | --- | --- |
| `prefix`, `tags`, `service`, `response_schema` | | bắt buộc (`tags` mặc định = tên model) |
| `create_schema` / `update_schema` | `None` | thiếu thì không sinh nhóm create / update |
| `import_schema` | `create_schema` | **ghi đè model dữ liệu import** (cột Excel + validate) |
| `import_key` | `"id"` | cột để khớp bản ghi khi import update/upsert (id hoặc cột unique, vd. `sku`) |
| `enable_import` / `enable_export` | `True` | bật/tắt import, export Excel |
| `disabled_routes` | `()` | tắt route theo key hoặc theo nhóm: `(Route.DELETE_ALL, RouteGroup.IMPORT)` |
| `auth_required` | `True` | auth cho **cả model** |
| `roles` | `None` | role cho **cả model** (có 1 trong các role); `None` = chỉ cần đăng nhập |
| `permission_prefix` | `None` | yêu cầu permission `<prefix>:<nhóm>` |
| `route_config` | `{}` | cấu hình **từng API** (theo key) hoặc từng nhóm, ưu tiên key |
| `list_limit`, `export_limit`, `import_max_rows`, `import_max_file_size_mb` | theo `.env` | giới hạn (`0` = không giới hạn) |

```python
class ProductAPI(BaseAPI):
    ...
    roles = [UserRole.ADMIN, "manager"]                    # mặc định cho cả model
    disabled_routes = (Route.DELETE_ALL,)
    route_config = {
        RouteGroup.READ: RouteConfig(auth=False),          # nhóm read: public
        RouteGroup.EXPORT: RouteConfig(roles=[UserRole.ADMIN, "manager", "viewer"]),
        Route.DELETE_ONE: RouteConfig(roles=[UserRole.ADMIN]),  # riêng 1 API
        RouteGroup.IMPORT: RouteConfig(permissions=[permission("product", RouteGroup.IMPORT)]),
        Route.CREATE_ONE: RouteConfig(dependencies=[check_quota]),  # dependency tuỳ ý
        Route.UPDATE_ALL: RouteConfig(enabled=False),
    }
```

`RouteConfig(enabled, auth, roles, permissions, dependencies)`: giá trị `None` = kế thừa cấu hình của class. Cấu hình theo `Route` (1 API) được ưu tiên hơn theo `RouteGroup` (cả nhóm).

**Hằng số / enum** — mọi tuỳ chọn cố định nằm ở `app/utils/enums.py` (`StrEnum`, so sánh bằng với chuỗi tương ứng nên chuỗi cũ vẫn chạy, nhưng nên dùng enum để IDE gợi ý và bắt lỗi chính tả):

| Enum | Giá trị |
| --- | --- |
| `Route` | key của 22 API: `GET_PAGE`, `CREATE_ONE`, `PATCH_MANY`, `DELETE_ALL`, `EXPORT_DATA`, ... |
| `RouteGroup` | `READ`, `CREATE`, `UPDATE`, `DELETE`, `IMPORT`, `EXPORT` (cũng là phần action của permission) |
| `FilterOperator`, `LogicalOperator` | toán tử filter; `AND`, `OR`, `NOT` |
| `ImportMode`, `ExportFormat` | `INSERT`/`UPDATE`/`UPSERT`; `XLSX`/`CSV` |
| `QueryParam` | tên query param dành riêng (`page`, `sort`, `filters`, ...) |
| `UserRole`, `AuthProvider`, `Environment` | role; `LOCAL`/`KEYCLOAK`; `DEV`/`TEST`/`STAGING`/`PROD` |

Permission: `permission("product", RouteGroup.READ)` → `"product:read"`, `ALL_PERMISSIONS` = `"*"` (`app/core/permissions.py`).

**BasePublicAPI**: kế thừa `BaseAPI` nhưng bỏ hoàn toàn auth và role, mọi route đều public:

```python
class CategoryAPI(BasePublicAPI):
    prefix = "/categories"
    service = CategoryService
    response_schema = CategoryResponse
    create_schema = CategoryRequest
```

### Import / Export Excel

**Import** — quy trình 3 bước, tất cả dòng hợp lệ mới ghi (1 transaction), có lỗi thì không ghi gì:

1. `GET /import/template` → file mẫu: sheet `data` có header (cột bắt buộc màu đỏ, comment ghi kiểu dữ liệu), sheet `guide` mô tả từng cột.
2. `POST /import/validate?mode=...` (file `multipart/form-data`) → kết quả kiểm tra, không ghi DB.
3. `POST /import?mode=...` → ghi; có lỗi thì trả 422 kèm danh sách lỗi.

| Mode | Hành vi |
| --- | --- |
| `insert` | mọi dòng là bản ghi mới (cột `id` bị bỏ qua) |
| `update` | mỗi dòng phải khớp bản ghi có sẵn theo `import_key`; chỉ ô có dữ liệu được ghi |
| `upsert` | khớp thì update, không khớp thì insert |

Lỗi trả về theo từng dòng, từng cột:

```json
{"row": 5, "column": "C", "field": "price", "message": "Input should be greater than or equal to 0", "value": -5}
```

Kiểm tra sẵn có: kiểu dữ liệu và ràng buộc của schema, bản ghi không tồn tại (update), **trùng giá trị unique** trong file hoặc với dữ liệu đã có. Header khớp theo tên field, alias hoặc `title`; cột lạ bị bỏ qua (trả về trong `ignored_columns`). Ô số trong cột text tự thành chuỗi, cột danh sách nhận JSON hoặc `a, b, c`.

Mỗi bước là một hàm của service, ghi đè để tuỳ biến theo model:

| Bước | Hàm | Dùng để |
| --- | --- | --- |
| Nhận dữ liệu | `import_read(source, ctx, max_rows)` | đọc file khác, map header khác |
| | `import_transform_row(values, ctx)` | chuẩn hoá giá trị thô (trim, lower, đổi mã → id, ...) |
| Validate | `import_validate(rows, ctx)` | toàn bộ quy trình validate |
| | `import_validate_row(row, ctx)` → `{field: lỗi}` | rule nghiệp vụ từng dòng; được sửa `row.data` |
| | `import_validate_unique(rows, ctx)` | kiểm tra trùng giữa các dòng |
| Ghi DB | `import_save(rows, ctx, result)` / `import_save_row(row, ctx)` | cách ghi. Mặc định: chạy `before_*` từng dòng, ghi theo lô `import_batch_size` (1000), `after_*` chạy sau mỗi lô (đã có `id`) |

Ví dụ: file import dùng **tên danh mục** thay vì id (`import_schema` riêng + đổi ở bước validate):

```python
class ProductImport(BaseSchema):
    name: str = Field(title="Tên sản phẩm")
    sku: str
    price: Decimal = Decimal(0)
    category_name: str | None = None


class ProductService(BaseService[Product, ProductCreateRequest, ProductUpdateRequest]):
    model = Product

    def import_validate_row(self, row, ctx):
        name = row.data.pop("category_name", None)
        if name is None:
            return {}
        category = self.db.scalar(select(Category).where(Category.name == name))
        if category is None:
            return {"category_name": f"Không có danh mục '{name}'"}
        row.data["category_id"] = category.id
        return {}

    def import_export_value(self, obj, name):           # để export_importable xuất đúng cột này
        if name == "category_name":
            return obj.category.name if obj.category else None
        return super().import_export_value(obj, name)


class ProductAPI(BaseAPI):
    ...
    import_schema = ProductImport
    import_key = "sku"
```

**Export**

- `GET /export?fields=id,name,category.name,tags,items&<filter/search/sort>`: chọn cột (mặc định mọi cột không ẩn), lọc như API đọc.
  - Cột thường, quan hệ 1 (`category.name`) → 1 cột giá trị; quan hệ 1 không chọn field con (`category`) → object JSON.
  - Quan hệ nhiều (`items`, `items.name`) và cột ARRAY → mảng JSON (`["a","b"]`).
  - Quan hệ được nạp bằng `selectinload` (không N+1). Text bắt đầu bằng `=` không bao giờ thành công thức (xlsx: ô kiểu text, csv: thêm `'`).
- `GET /export/importable`: cùng cột với file mẫu import (kèm `import_key`). Sửa file rồi import lại bằng `mode=update`/`upsert`.

**Dữ liệu lớn**

Export **không giới hạn số dòng** (`EXPORT_MAX_ROWS=0`). Dữ liệu được đọc từ DB theo lô 1000 dòng (server-side cursor), nên RAM gần như không đổi dù file lớn tới đâu.

| | `format=xlsx` (mặc định) | `format=csv` |
| --- | --- | --- |
| Cách trả về | dựng file trên đĩa (file tạm), xong mới stream về client, rồi xoá file tạm | stream ngay khi đọc được dòng |
| Byte đầu tiên | sau khi dựng xong toàn bộ | gần như tức thì |
| Đo với 300.000 dòng | ~21s, 7,9 MB | byte đầu 0,4s, xong 8,7s, 21,7 MB |
| Giới hạn | 1.048.576 dòng/sheet, vượt thì tự sang sheet `data_2`, `data_3`... | không |

Export xlsx rất lớn có thể vượt timeout của reverse proxy (nginx mặc định 60s) vì client chưa nhận byte nào trong lúc dựng file. Khi đó tăng `proxy_read_timeout` hoặc dùng `format=csv` (file mở được bằng Excel, có BOM UTF-8 nên tiếng Việt hiển thị đúng).

Import tối đa **100 MB** (`IMPORT_MAX_FILE_SIZE_MB`) và **100.000 dòng** (`IMPORT_MAX_ROWS`, `0` = không giới hạn). File upload được giữ trên đĩa, không nạp vào RAM. Vì cơ chế "tất cả hoặc không gì", mọi dòng được validate trong RAM (~1–2 KB/dòng) trước khi ghi, rồi ghi trong 1 transaction theo lô 1000 dòng. Đo được: 100.000 dòng ~17s, RAM +75 MB. Muốn nhận file lớn cần tăng giới hạn của reverse proxy (nginx: `client_max_body_size 100m;`, `proxy_read_timeout`).

### BaseService

Dùng trong endpoint tự viết: `service: Annotated[ProductService, Depends()]` (session DB được inject). Ngoài request: `ProductService(SessionLocal())`.

| Đọc | Ghi |
| --- | --- |
| `get_by_id(id)` (404), `get_by_id_optional(id)`, `get_one_by(**cond)`, `exists(**cond)` | `create(data)`, `create_many(items)` |
| `get_first(q)`, `get_list(q, limit)`, `get_page(q, pagination)`, `count(q)` | `update(obj, data, partial=True)`, `update_by_id`, `partial_update_by_id` |
| `get_many(ids)` | `update_many(items, partial)`, `update_all(q, data, partial)` |
| `build_query(q)` → `Select` để tự viết tiếp | `delete(obj, hard=False)`, `delete_by_id`, `delete_many(ids)`, `delete_all(q)` |
| `export_data(q, fields)` → `(headers, rows)` (rows đọc dần) | `import_excel(file, schema=, mode=)` |

`q` nhận `QuerySpec`, dict viết tắt hoặc list JSON y như API: `service.get_list({"price__gte": 10, "category.name": "fruit"})`, hoặc dựng bằng enum: `QuerySpec(filters=[Condition("price", FilterOperator.GTE, 10), Group(LogicalOperator.OR, [...])], sort=["-price"])` (`app.utils.query_builder`). Mọi hàm ghi có `commit=False` để gộp nhiều thao tác trong 1 transaction.

Hook nghiệp vụ: `before_create(data) -> data`, `after_create(obj)`, `before_update(obj, data) -> data`, `after_update(obj)`, `before_delete(obj)`, `after_delete(obj)`. Override `get_query()` để thêm join/eager-load hoặc lọc theo dòng — áp dụng cho mọi API đọc, bulk, export.

Ví dụ phân quyền theo dòng (user chỉ thấy/sửa sản phẩm của mình, admin thấy hết):

```python
from app.core.database import DbSession
from app.utils.login_manager import CurrentUser


class ProductService(BaseService[Product, ProductCreateRequest, ProductUpdateRequest]):
    model = Product

    def __init__(self, db: DbSession, user: CurrentUser):   # FastAPI inject cả 2
        super().__init__(db)
        self.user = user

    def get_query(self):
        stmt = super().get_query()
        if self.user.has_role("admin"):
            return stmt
        return stmt.where(Product.owner_id == self.user.id)

    def before_create(self, data):
        data["owner_id"] = self.user.id
        return data
```

## Xác thực

| Cách | Cách dùng | Bật/tắt |
| --- | --- | --- |
| JWT local | `POST /api/auth/login` → `Authorization: Bearer <access_token>` | `AUTH_LOCAL_ENABLED` |
| HTTP Basic | `Authorization: Basic base64(user:pass)` trên mọi endpoint | `AUTH_BASIC_ENABLED` |
| Keycloak | `Authorization: Bearer <access token của Keycloak>` | `KEYCLOAK_ENABLED` |

Backend phân biệt JWT local và token Keycloak bằng claim `iss`, nên client không cần chỉ rõ loại token.

**JWT local**: `POST /auth/login` (JSON) hoặc `POST /auth/token` (form, cho Swagger) trả `access_token` + `refresh_token`. `POST /auth/refresh` lấy token mới. `POST /auth/logout` và `POST /auth/change-password` tăng `users.token_version`, khiến **mọi token cũ của user bị thu hồi** (mọi thiết bị). Đổi password qua admin (PATCH /users) cũng thu hồi token.

**Keycloak SSO**:
- Access token được verify **offline** bằng public key của realm (JWKS, cache 5 phút): chữ ký, `iss`, `exp`, `aud` (= `KEYCLOAK_AUDIENCE`, mặc định là `KEYCLOAK_CLIENT_ID`), `typ=Bearer` (không nhận ID token). Không gọi Keycloak cho mỗi request.
- Lần đầu gặp một `sub`, backend tạo user local (`auth_provider=keycloak`); nếu email đã verified trùng một tài khoản local chưa liên kết thì liên kết vào tài khoản đó. Tắt bằng `KEYCLOAK_AUTO_CREATE_USER=false`.
- Role hiệu lực = role trong DB ∪ realm roles ∪ client roles (backend/frontend client) trong token.
- Khoá user local (`is_active=false`) cũng chặn được user SSO.

Các luồng đăng nhập Keycloak:

| Luồng | Endpoint |
| --- | --- |
| SPA tự dùng thư viện OIDC (keycloak-js, oidc-client-ts) với client public PKCE | lấy cấu hình ở `GET /api/auth/sso/config`, rồi gửi token lên API như bình thường |
| Backend điều phối (mở bằng trình duyệt) | `GET /api/auth/sso/authorize` → trang login Keycloak → `GET /api/auth/sso/callback` trả token |
| Frontend tự nhận `?code=` | `POST /api/auth/sso/token {code, redirect_uri, code_verifier}` |
| Username/password (Direct Access Grant) | `POST /api/auth/sso/login` |
| Refresh / logout | `POST /api/auth/sso/refresh`, `POST /api/auth/sso/logout` |

### Keycloak SSO

Backend dùng Keycloak **có sẵn bên ngoài**. Cấu hình trong `.env`:

| Biến | Ý nghĩa |
| --- | --- |
| `KEYCLOAK_SERVER_URL` | URL backend (trong container) gọi tới Keycloak: lấy JWKS, đổi token. Keycloak chạy trên chính máy này: `http://host.docker.internal:<port>` |
| `KEYCLOAK_PUBLIC_URL` | URL trình duyệt dùng, cũng là `iss` trong token. Để trống nếu giống `KEYCLOAK_SERVER_URL` |
| `KEYCLOAK_REALM` | tên realm |
| `KEYCLOAK_CLIENT_ID` / `KEYCLOAK_CLIENT_SECRET` | client confidential của backend |
| `KEYCLOAK_FRONTEND_CLIENT_ID` | client public (PKCE) cho Swagger/SPA |
| `KEYCLOAK_AUDIENCE` | giá trị bắt buộc có trong `aud`; mặc định = `KEYCLOAK_CLIENT_ID` |

`iss` của token phải đúng bằng `KEYCLOAK_PUBLIC_URL/realms/<realm>`, nếu không mọi request SSO sẽ bị 401. Kiểm tra bằng cách decode một access token (jwt.io) và so trường `iss`.

Cần tạo trong realm của bạn:

1. **Client backend** (vd. `fastapi-backend`): *Client authentication* = On (có secret). Bật *Standard flow*; bật *Direct access grants* nếu dùng `POST /auth/sso/login`. *Valid redirect URIs*: `http://localhost:8000/*` và domain frontend.
2. **Client frontend** (vd. `fastapi-frontend`): *Client authentication* = Off, *Standard flow* = On, PKCE `S256`. *Valid redirect URIs*: `http://localhost:8000/docs/oauth2-redirect` (Swagger) và domain frontend; *Web origins*: `+`.
3. **Audience mapper** trên cả hai client (*Client scopes → <client>-dedicated → Add mapper → Audience*): *Included Client Audience* = client backend, *Add to access token* = On. Thiếu mapper này, token không có `aud` của backend và bị từ chối.
4. **Role**: tạo realm role (hoặc client role của backend) trùng tên với role trong `app/core/permissions.py`, vd. `admin`, `user`.

Đăng nhập bằng Google/Microsoft/LDAP: cấu hình **Identity Provider / User Federation trong Keycloak**, backend không phải sửa gì.

## Phân quyền

```python
from app.utils.login_manager import CurrentUser, OptionalUser, PermissionRequired, RoleRequired


@router.get("/me")
def me(user: CurrentUser): ...                       # bắt buộc đăng nhập

@router.get("/public")
def public(user: OptionalUser): ...                  # user hoặc None

@router.post("/approve", dependencies=[Depends(RoleRequired("admin", "manager"))])  # 1 trong các role
@router.delete("/{id}", dependencies=[Depends(PermissionRequired("product:delete"))])
```

Map role → permission ở `app/core/permissions.py`:

```python
ROLE_PERMISSIONS = {
    UserRole.ADMIN: frozenset({ALL_PERMISSIONS}),               # mọi quyền
    "manager": frozenset({
        permission("product", ALL_PERMISSIONS),                 # product:*
        permission("user", RouteGroup.READ),                    # user:read
    }),
}
```

Đặt tên role giống hệt role trong Keycloak để dùng chung cho cả user local và user SSO.

## Response

```json
// thành công
{"http_code": 200, "success": true, "message": null, "data": {...}}
// danh sách
{"http_code": 200, "success": true, "message": null, "data": [...],
 "metadata": {"page": 1, "page_size": 20, "total": 42, "total_pages": 3}}
// lỗi (4xx/5xx)
{"http_code": 422, "success": false, "message": "email: field required",
 "errors": [{"field": "email", "message": "Field required", "type": "missing"}]}
```

Ném lỗi ở bất kỳ đâu: `raise CustomException(ExceptionType.NOT_FOUND, "Product not found")`. Lỗi ràng buộc DB được map tự động (unique → 409, FK → 409, NOT NULL → 400). Lỗi không bắt được → 500, chỉ hiện chi tiết khi `DEBUG=true`. Mọi response có header `X-Request-ID`, cùng giá trị với request id trong log.

## Migration

```bash
make migration m="add products"   # autogenerate (so sánh models với DB)
make migrate                      # upgrade head + seed admin
make downgrade                    # lùi 1 bản
docker compose run --rm --no-deps app alembic check   # models và migration có lệch không
```

Không dùng `create_all`; schema chỉ thay đổi qua Alembic.

## Test

```bash
make test     # pytest trong container, DB riêng <POSTGRES_DB>_test (tự tạo)
```

Test dùng PostgreSQL thật. Token Keycloak được giả lập bằng khoá RSA sinh trong test nên không cần Keycloak chạy. `tests/crud_resources.py` là ví dụ một module đầy đủ (model + schema + service + router) dùng để test base CRUD.

## Thay đổi so với bản cũ

- Timestamp chuyển từ `Float` epoch sang `timestamptz` (ISO 8601 trong JSON); `dob`, `identity_card_date` sang `date`. Role dùng chữ thường (`admin`, `user`, `guest`), khớp với Keycloak.
- `/auth/login-keycloak` → `/auth/sso/login`. Bỏ `/users/all` (dùng `?page_size=`). `DELETE` trả 200 kèm envelope.
- Bỏ xác thực Google trực tiếp: thêm Google làm Identity Provider trong Keycloak.
- `PermissionRequired` giờ kiểm tra permission; kiểm tra role dùng `RoleRequired`.
- Bỏ `fastapi-sqlalchemy` (dùng `DbSession` dependency) và `passlib` (dùng `pwdlib`, vẫn verify được hash bcrypt cũ).
- Migration cũ (rỗng) được thay bằng migration tạo bảng `users`. DB tạo bằng bản cũ cần tạo lại: `make clean && make up`.
