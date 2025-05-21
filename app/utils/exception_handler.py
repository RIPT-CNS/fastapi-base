import enum
from typing import Optional

from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import ValidationException
from fastapi.responses import JSONResponse
from app.schemas.sche_response import BaseResponse


class ExceptionType(enum.Enum):
    BAD_REQUEST = 400, "Client unknown error"
    BAD_REQUEST_DATA_MISMATCH = 400, "Client error: Incorrect passed data"
    BAD_REQUEST_TYPE_MISMATCH = 400, "Client error: Incorrect passed data type"
    BAD_REQUEST_FORMAT_MISMATCH = 400, "Client error: Incorrect passed data format"
    UNAUTHORIZED = 401, "Unauthorized"
    FORBIDDEN = 403, "Don't have access rights to the content"
    NOT_FOUND = 404, "Resource not found"
    CONFLICT = 409, "Resource already exists"
    INTERNAL_SERVER_ERROR = 500, "Something went wrong"

    def __new__(cls, *args, **kwds):
        value = len(cls.__members__) + 1
        obj = object.__new__(cls)
        obj._value_ = value
        return obj

    def __init__(self, http_code, message):
        self.http_code = http_code
        self.message = message


class CustomException(Exception):
    http_code: int
    message: str
    exception: ExceptionType

    def __init__(
        self,
        http_code: Optional[int] = None,
        message: Optional[str] = None,
        exception: Optional[ExceptionType] = None,
    ):
        if exception and (
            type(exception) is ExceptionType or type(exception) is CustomException
        ):
            self.http_code = exception.http_code
            self.message = exception.message
        else:
            self.http_code = http_code
            self.message = message


async def fastapi_error_handler(request, exc: Exception):
    print(f"========== Exception ==========", flush=True)
    return JSONResponse(
        status_code=ExceptionType.INTERNAL_SERVER_ERROR.http_code,
        content=jsonable_encoder(
            BaseResponse(
                http_code=ExceptionType.INTERNAL_SERVER_ERROR.http_code,
                message=ExceptionType.INTERNAL_SERVER_ERROR.message,
            )
        ),
    )


async def custom_error_handler(request, exc: CustomException):
    print(f"========== CustomException ==========", flush=True)
    if not exc.http_code:
        exc.http_code = ExceptionType.INTERNAL_SERVER_ERROR.http_code
    if not exc.message:
        exc.message = ExceptionType.INTERNAL_SERVER_ERROR.message
    return JSONResponse(
        status_code=exc.http_code,
        content=jsonable_encoder(
            BaseResponse(http_code=exc.http_code, message=exc.message)
        ),
    )


async def validation_exception_handler(request, exc: ValidationException):
    print(f"========== ValidationException ==========", flush=True)
    return JSONResponse(
        status_code=422,
        content=jsonable_encoder(
            BaseResponse(
                http_code=422,
                message=get_message_validation(exc),
            )
        ),
    )


def get_message_validation(exc: ValidationException) -> str:
    message = ""
    for error in exc.errors():
        message += str(error.get("loc")[1]) + ": " + error.get("msg") + "; "
    message = message[:-2]
    return message
