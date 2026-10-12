# FASTAPI_BASE

Backend base: **FastAPI + PostgreSQL + SQLAlchemy 2 + Alembic + Keycloak**, chạy hoàn toàn bằng Docker.

- **Một lệnh là chạy đủ**: PostgreSQL, Keycloak (đã có sẵn realm/client/role/user demo), migration, tạo admin, API (hot reload).
- **Gọn**: 1 `Dockerfile`, 1 `docker-compose.yml`, 1 `requirements.txt`. Dev hay prod chỉ khác nhau ở `.env`.
- **Xác thực**: JWT local (access + refresh, thu hồi token), HTTP Basic, SSO Keycloak (verify JWT offline qua JWKS, tự tạo user lần đầu đăng nhập).
- **Phân quyền**: theo role (local + role từ Keycloak) và theo permission (`resource:action`, có wildcard).
- **CRUD generic**: khai báo model + schema + service + 1 router là có đủ list/get/create/put/patch/delete với phân trang, lọc, tìm kiếm, sắp xếp, soft delete.
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
| Keycloak admin | http://localhost:8080 | admin / admin |
| Realm `fastapi-base` | | sso-admin, sso-user / `Demo@123` |
| PostgreSQL | localhost:5432 | postgres / postgres |

Cổng host đổi trong `.env`: `APP_PORT`, `KEYCLOAK_PORT`, `DB_PORT`.

Thứ tự khởi động: `db` (healthy) → `migrate` (`alembic upgrade head` + tạo admin, rồi thoát) → `app`. `keycloak` chạy song song (khi `COMPOSE_PROFILES=keycloak`), app không phụ thuộc Keycloak lúc khởi động.

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
│   │   └── v1/api_user.py      # CRUD users (tự động mount ở /api/v1/users)
│   ├── core
│   │   ├── config.py           # Settings (đọc env / .env), validate cấu hình prod
│   │   ├── database.py         # engine, get_db, DbSession
│   │   ├── security.py         # hash password (argon2/bcrypt), JWT local
│   │   ├── keycloak.py         # OIDC client: verify JWT qua JWKS, token/refresh/logout
│   │   ├── permissions.py      # map role -> permission
│   │   ├── crud_router.py      # CRUDRouter: sinh REST endpoint từ service
│   │   ├── router.py           # tự động include app/api/v*/api_*.py
│   │   ├── logging.py, middleware.py
│   ├── models                  # model_*.py được import tự động (Alembic thấy ngay)
│   ├── schemas                 # sche_*.py: Pydantic request/response
│   ├── services                # srv_base.py (BaseService), srv_user.py, srv_auth.py
│   ├── utils                   # login_manager.py (dependency auth), exception_handler.py, ...
│   ├── cli.py                  # python -m app.cli serve | migrate | seed | create-user
│   └── main.py
├── alembic/versions            # migration
├── docker
│   ├── keycloak/realm.json     # realm import sẵn cho dev
│   └── postgres/init           # tạo DB cho Keycloak
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
| `COMPOSE_PROFILES` | `keycloak` (chạy Keycloak kèm realm demo) | để trống nếu dùng Keycloak bên ngoài |
| `KEYCLOAK_SERVER_URL` / `KEYCLOAK_PUBLIC_URL` | `http://keycloak:8080` / `http://localhost:8080` | `https://sso.example.com` |
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
COMPOSE_PROFILES=                   # Keycloak bên ngoài
KEYCLOAK_SERVER_URL=https://sso.example.com
KEYCLOAK_PUBLIC_URL=https://sso.example.com
KEYCLOAK_CLIENT_SECRET=<secret của client>
```

Code được mount vào container (`.:/app`) ở mọi môi trường: cập nhật prod bằng `git pull && docker compose up -d --build` (chạy lại migrate + restart app). Muốn image bất biến (đẩy lên registry) thì bỏ dòng `volumes: - .:/app` trong `docker-compose.yml`.

Muốn tự host Keycloak ở prod: giữ `COMPOSE_PROFILES=keycloak`, đặt `KEYCLOAK_MODE=start`, `KEYCLOAK_PUBLIC_URL=https://sso...`, đổi `KEYCLOAK_ADMIN_PASSWORD`, `KEYCLOAK_DEMO_PASSWORD` (hoặc xoá user demo sau khi import), và đặt reverse proxy HTTPS phía trước.

Đặt reverse proxy (nginx/traefik) có TLS phía trước app; uvicorn đã bật proxy headers.

Chạy không dùng Docker: `pip install -r requirements.txt`, trong `.env` sửa `POSTGRES_HOST=localhost`, `POSTGRES_PORT=<DB_PORT>`, `KEYCLOAK_SERVER_URL=http://localhost:<KEYCLOAK_PORT>`, rồi `python -m app.cli migrate && python -m app.cli serve`.

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
    search_fields = ("name", "sku")                    # ?search=
    filter_fields = {                                  # ?category=..&price__gte=..
        "category": ("eq", "in"),
        "price": ("gte", "lte"),
    }
    sort_fields = ("id", "name", "price", "created_at")  # ?sort_by=&order=asc|desc
```

**4. Router** — `app/api/v1/api_product.py` (file `api_*.py` trong `app/api/vN/` được mount tự động)

```python
from app.core.crud_router import CRUDRouter
from app.schemas.sche_product import ProductCreateRequest, ProductResponse, ProductUpdateRequest
from app.services.srv_product import ProductService

router = CRUDRouter(
    prefix="/products",
    tags=["Products"],
    service=ProductService,
    response_schema=ProductResponse,
    create_schema=ProductCreateRequest,
    update_schema=ProductUpdateRequest,
    permissions={"list": None, "get": None},   # list/get public
    permission_prefix="product",               # còn lại cần product:create / update / delete
)
```

**5. Migration**

```bash
make migration m="add products"   # tạo file trong alembic/versions — đọc lại trước khi commit
make migrate
```

Kết quả: `GET/POST /api/v1/products`, `GET/PUT/PATCH/DELETE /api/v1/products/{item_id}`, và alias `/api/products` (vì `API_VERSION=v1`).

### CRUDRouter

| Tham số | Ý nghĩa |
| --- | --- |
| `service`, `response_schema` | bắt buộc |
| `create_schema` / `update_schema` | bỏ trống thì không sinh route create / update+patch |
| `exclude=("update", "delete")` | bỏ route. Action: `list`, `get`, `create`, `update` (PUT), `patch`, `delete` |
| `permission_prefix="product"` | list/get → `product:read`, create → `product:create`, PUT/PATCH → `product:update`, delete → `product:delete` |
| `permissions={...}` | ghi đè theo action: `None` = public, `["admin", "editor"]` = có một trong các role, hoặc 1 dependency bất kỳ, vd. `PermissionRequired("x:y")` |
| `auth_required=True` | action không cấu hình gì thì yêu cầu đăng nhập |

PATCH chỉ ghi các field client gửi lên. PUT ghi **toàn bộ** field của `update_schema` (field không gửi nhận giá trị mặc định).

### BaseService

Dùng trong endpoint tự viết: `service: Annotated[ProductService, Depends()]` (session DB được inject). Ngoài request: `ProductService(SessionLocal())`.

| Đọc | Ghi |
| --- | --- |
| `get_by_id(id)` — 404 nếu không có | `create(data)` |
| `get_by_id_optional(id)` | `update(obj, data, partial=True)` |
| `get_one_by(**cond)`, `exists(**cond)`, `count(filters)` | `update_by_id(id, data)` (PUT), `partial_update_by_id(id, data)` (PATCH) |
| `get_by_filter(pagination, sort, filters, search)` → `(items, metadata)` | `delete(obj, hard=False)`, `delete_by_id(id)` |
| `get_all(sort, filters, search)` — không phân trang | mọi hàm ghi có `commit=False` để gộp nhiều thao tác trong 1 transaction |

Toán tử lọc (`field__op`): `eq` (tên field trơn), `ne`, `gt`, `gte`, `lt`, `lte`, `in`, `not_in`, `like` (ILIKE chứa, đã escape), `isnull`. Với cột ARRAY: `eq` = chứa phần tử, `in` = giao nhau.

Hook để viết nghiệp vụ: `before_create(data) -> data`, `after_create(obj)`, `before_update(obj, data) -> data`, `after_update(obj)`, `before_delete(obj)`, `after_delete(obj)`. Override `get_query()` để thêm join/eager-load hoặc lọc theo dòng.

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

Realm demo (`docker/keycloak/realm.json`, chỉ import khi realm chưa tồn tại):
- client `fastapi-backend` (confidential, có Direct Access Grant) và `fastapi-frontend` (public, PKCE, dùng cho Swagger/SPA); cả hai có audience mapper đưa `fastapi-backend` vào `aud`;
- realm roles `admin`, `user`, `guest`; user `sso-admin` (admin) và `sso-user` (user).

Đăng nhập bằng Google/Microsoft/LDAP: cấu hình **Identity Provider / User Federation trong Keycloak**, backend không phải sửa gì.

Trong Docker dev, backend gọi Keycloak qua `http://keycloak:8080` (`KEYCLOAK_SERVER_URL`), còn trình duyệt và issuer của token dùng `http://localhost:KEYCLOAK_PORT` (`KEYCLOAK_PUBLIC_URL`). Keycloak được cấu hình `KC_HOSTNAME` cố định + `KC_HOSTNAME_BACKCHANNEL_DYNAMIC=true` để `iss` luôn khớp.

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
    UserRole.ADMIN: frozenset({"*"}),                           # mọi quyền
    "manager": frozenset({"product:*", "user:read"}),
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
