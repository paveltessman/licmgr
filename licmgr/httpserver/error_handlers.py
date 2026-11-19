import logging
from collections.abc import Mapping
from http import HTTPStatus

from fastapi import FastAPI
from fastapi import Request
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException
from starlette.responses import JSONResponse

from .schemas import ApiError
from .schemas import ErrorResponse

logger = logging.getLogger(__name__)


def error_response(
    status: int,
    *,
    code: str,
    message: str,
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    r = JSONResponse(
        content=ErrorResponse(error=ApiError(code=code, message=message)).model_dump(),
        status_code=status,
        headers=headers,
    )
    return r


async def handle_http_error(request: Request, error: Exception) -> JSONResponse:

    assert isinstance(error, HTTPException)

    try:
        status = HTTPStatus(error.status_code)
    except ValueError:
        code = f"http_{error.status_code}"
        message = "HTTP request failed"
    else:
        code = status.name.lower()
        message = status.phrase
    r = error_response(
        error.status_code,
        code=code,
        message=message,
        headers=error.headers,
    )
    return r


async def handle_validation_error(request: Request, error: Exception) -> JSONResponse:
    r = error_response(
        422,
        code="invalid_request",
        message="Request validation failed",
    )
    return r


async def handle_unexpected_error(request: Request, error: Exception) -> JSONResponse:
    logger.error("Unhandled HTTP error (%s)", type(error).__name__)
    return error_response(500, code="internal_error", message="Internal server error")


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(HTTPException, handle_http_error)
    app.add_exception_handler(RequestValidationError, handle_validation_error)
    app.add_exception_handler(Exception, handle_unexpected_error)
