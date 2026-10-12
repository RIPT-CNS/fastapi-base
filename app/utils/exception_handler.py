import enum
import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.config import settings
from app.schemas.sche_response import ErrorResponse

logger = logging.getLogger(__name__)


class ExceptionType(enum.Enum):
    BAD_REQUEST = 400, "Bad request"
    BAD_REQUEST_DATA_MISMATCH = 400, "Client error: Incorrect passed data"
    BAD_REQUEST_TYPE_MISMATCH = 400, "Client error: Incorrect passed data type"
    BAD_REQUEST_FORMAT_MISMATCH = 400, "Client error: Incorrect passed data format"
    UNAUTHORIZED = 401, "Unauthorized"
    FORBIDDEN = 403, "Don't have access rights to the content"
    NOT_FOUND = 404, "Resource not found"
    CONFLICT = 409, "Resource already exists"
    PAYLOAD_TOO_LARGE = 413, "Payload too large"
    UNPROCESSABLE_ENTITY = 422, "Validation error"
    INTERNAL_SERVER_ERROR = 500, "Something went wrong"
    SERVICE_UNAVAILABLE = 503, "Service unavailable"

    def __new__(cls, *args, **kwds):
        value = len(cls.__members__) + 1
        obj = object.__new__(cls)
        obj._value_ = value
        return obj

    def __init__(self, http_code: int, message: str):
        self.http_code = http_code
        self.message = message


class CustomException(Exception):
    """Raise anywhere (service, dependency, endpoint) to return a standard error response.

    raise CustomException(ExceptionType.NOT_FOUND)
    raise CustomException(ExceptionType.CONFLICT, "Email already exists")
    raise CustomException(http_code=418, message="I'm a teapot")
    """

    def __init__(
        self,
        exception: ExceptionType | None = None,
        message: str | None = None,
        *,
        http_code: int | None = None,
        errors: list[dict[str, Any]] | None = None,
        headers: dict[str, str] | None = None,
    ):
        exception = exception or ExceptionType.INTERNAL_SERVER_ERROR
        self.http_code = http_code or exception.http_code
        self.message = message or exception.message
        self.errors = errors
        self.headers = headers
        super().__init__(self.message)


def _error_response(
    http_code: int,
    message: str,
    errors: list[dict[str, Any]] | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    body = ErrorResponse(http_code=http_code, message=message, errors=errors)
    return JSONResponse(
        status_code=http_code, content=body.model_dump(mode="json"), headers=headers
    )


async def custom_exception_handler(request: Request, exc: CustomException) -> JSONResponse:
    return _error_response(exc.http_code, exc.message, exc.errors, exc.headers)


async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    return _error_response(exc.status_code, str(exc.detail), headers=getattr(exc, "headers", None))


async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    errors = []
    for error in exc.errors():
        # loc = ("body" | "query" | "path", field, ...)
        loc = [str(part) for part in error.get("loc", ())]
        field = ".".join(loc[1:]) if len(loc) > 1 else ".".join(loc)
        errors.append({"field": field, "message": error.get("msg"), "type": error.get("type")})
    message = "; ".join(f"{e['field']}: {e['message']}" for e in errors) or "Validation error"
    return _error_response(422, message, errors)


_INTEGRITY_ERRORS = {
    "23505": (409, "Resource already exists"),  # unique_violation
    "23503": (409, "Related resource does not exist or is still referenced"),  # foreign_key
    "23502": (400, "Missing required field"),  # not_null_violation
    "23514": (400, "Value violates a check constraint"),  # check_violation
}


async def integrity_error_handler(request: Request, exc: IntegrityError) -> JSONResponse:
    sqlstate = getattr(exc.orig, "sqlstate", None)
    http_code, message = _INTEGRITY_ERRORS.get(sqlstate, (400, "Data integrity error"))
    logger.warning("IntegrityError: %s", exc.orig)
    if settings.DEBUG:
        message = f"{message}: {exc.orig}"
    return _error_response(http_code, message)


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    message = ExceptionType.INTERNAL_SERVER_ERROR.message
    if settings.DEBUG:
        message = f"{type(exc).__name__}: {exc}"
    return _error_response(500, message)


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(CustomException, custom_exception_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(IntegrityError, integrity_error_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)
