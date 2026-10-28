"""Application errors and the handlers that turn every failure into the contract's error shape:

    {"status": "error", "code": "...", "message": "<Polish text>", "details": {...} | null}

Raise errors with the `error()` helper; the HTTP status comes from the code:

    raise error(ErrorCode.FILE_TOO_LARGE, file=upload.filename, limit_mb=250)
"""

import logging
from enum import StrEnum
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.messages import ERROR_MESSAGES

logger = logging.getLogger(__name__)


class ErrorCode(StrEnum):
    VALIDATION_ERROR = "VALIDATION_ERROR"
    INVALID_EMAIL = "INVALID_EMAIL"
    UNAUTHENTICATED = "UNAUTHENTICATED"
    INVALID_OTP = "INVALID_OTP"
    OTP_EXPIRED = "OTP_EXPIRED"
    OTP_RATE_LIMITED = "OTP_RATE_LIMITED"
    TOO_MANY_ATTEMPTS = "TOO_MANY_ATTEMPTS"
    USER_LIMIT_REACHED = "USER_LIMIT_REACHED"
    NO_FILES = "NO_FILES"
    TOO_MANY_FILES = "TOO_MANY_FILES"
    FILE_TOO_LARGE = "FILE_TOO_LARGE"
    UNSUPPORTED_FORMAT = "UNSUPPORTED_FORMAT"
    CORRUPTED_FILE = "CORRUPTED_FILE"
    INVALID_TARGET = "INVALID_TARGET"
    FORBIDDEN = "FORBIDDEN"
    NOT_FOUND = "NOT_FOUND"
    FILE_EXPIRED = "FILE_EXPIRED"
    INTERNAL_ERROR = "INTERNAL_ERROR"


HTTP_STATUS: dict[ErrorCode, int] = {
    ErrorCode.VALIDATION_ERROR: 400,
    ErrorCode.INVALID_EMAIL: 400,
    ErrorCode.UNAUTHENTICATED: 401,
    ErrorCode.INVALID_OTP: 401,
    ErrorCode.OTP_EXPIRED: 401,
    ErrorCode.OTP_RATE_LIMITED: 429,
    ErrorCode.TOO_MANY_ATTEMPTS: 429,
    ErrorCode.USER_LIMIT_REACHED: 503,
    ErrorCode.NO_FILES: 400,
    ErrorCode.TOO_MANY_FILES: 400,
    ErrorCode.FILE_TOO_LARGE: 413,
    ErrorCode.UNSUPPORTED_FORMAT: 415,
    ErrorCode.CORRUPTED_FILE: 422,
    ErrorCode.INVALID_TARGET: 400,
    ErrorCode.FORBIDDEN: 403,
    ErrorCode.NOT_FOUND: 404,
    ErrorCode.FILE_EXPIRED: 410,
    ErrorCode.INTERNAL_ERROR: 500,
}


class AppError(Exception):
    def __init__(
        self,
        code: ErrorCode,
        message: str,
        http_status: int,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.http_status = http_status
        self.details = details


def error(code: ErrorCode, *, message: str | None = None, **details: Any) -> AppError:
    """Build an `AppError` for `code`. Keyword arguments fill the message template and are
    returned to the client as `details`. `message` replaces the default template."""
    template = message if message is not None else ERROR_MESSAGES[code]
    return AppError(code, template.format(**details), HTTP_STATUS[code], details or None)


def _response(
    code: ErrorCode, message: str, http_status: int, details: dict[str, Any] | None = None
) -> JSONResponse:
    return JSONResponse(
        status_code=http_status,
        content={"status": "error", "code": code, "message": message, "details": details},
    )


async def _handle_app_error(_request: Request, exc: AppError) -> JSONResponse:
    return _response(exc.code, exc.message, exc.http_status, exc.details)


async def _handle_validation_error(_request: Request, exc: RequestValidationError) -> JSONResponse:
    # loc looks like ("body", "email") – drop the "body"/"query"/... prefix.
    fields = {
        ".".join(str(part) for part in err["loc"][1:]) or str(err["loc"][0]): err["msg"]
        for err in exc.errors()
    }
    code = ErrorCode.VALIDATION_ERROR
    return _response(code, ERROR_MESSAGES[code], HTTP_STATUS[code], {"fields": fields})


_HTTP_EXCEPTION_CODES: dict[int, ErrorCode] = {
    401: ErrorCode.UNAUTHENTICATED,
    403: ErrorCode.FORBIDDEN,
    404: ErrorCode.NOT_FOUND,
    405: ErrorCode.NOT_FOUND,
}


async def _handle_http_exception(_request: Request, exc: StarletteHTTPException) -> JSONResponse:
    """Framework-raised errors (unknown route, wrong method, ...)."""
    if exc.status_code in _HTTP_EXCEPTION_CODES:
        code = _HTTP_EXCEPTION_CODES[exc.status_code]
        return _response(code, ERROR_MESSAGES[code], HTTP_STATUS[code])
    code = ErrorCode.VALIDATION_ERROR if exc.status_code < 500 else ErrorCode.INTERNAL_ERROR
    return _response(code, ERROR_MESSAGES[code], exc.status_code)


async def _handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled error on %s %s", request.method, request.url.path, exc_info=exc)
    code = ErrorCode.INTERNAL_ERROR
    return _response(code, ERROR_MESSAGES[code], HTTP_STATUS[code])


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, _handle_app_error)
    app.add_exception_handler(RequestValidationError, _handle_validation_error)
    app.add_exception_handler(StarletteHTTPException, _handle_http_exception)
    app.add_exception_handler(Exception, _handle_unexpected)
