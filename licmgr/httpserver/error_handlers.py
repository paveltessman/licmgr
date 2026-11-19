import logging
from collections.abc import Mapping
from collections.abc import Sequence
from http import HTTPStatus
from typing import cast

from fastapi import FastAPI
from fastapi import Request
from fastapi.exceptions import RequestValidationError
from pydantic_core import ErrorDetails
from starlette.exceptions import HTTPException
from starlette.responses import JSONResponse

from .schemas import ApiError
from .schemas import ErrorResponse
from licmgr.services.license.exceptions import DeviceLimitReachedError
from licmgr.services.license.exceptions import InvalidActivationRequestError
from licmgr.services.license.exceptions import InvalidLicenseError

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
    _ = request

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
    _ = request

    if isinstance(error, RequestValidationError):
        issues = cast(Sequence[ErrorDetails], error.errors())
        details = "; ".join(
            f"{'.'.join(map(str, issue['loc']))}: {issue['msg']}" for issue in issues
        )
    else:
        assert isinstance(error, InvalidActivationRequestError)
        details = str(error)

    r = error_response(
        422,
        code="invalid_request",
        message=f"Request validation failed: {details}",
    )
    return r


async def handle_unexpected_error(request: Request, error: Exception) -> JSONResponse:
    _ = request

    logger.exception(error)
    return error_response(500, code="internal_error", message="Internal server error")


async def handle_invalid_license(request: Request, error: Exception) -> JSONResponse:
    _ = request, error
    r = error_response(404, code="invalid_license", message="License key is not valid")
    return r


async def handle_device_limit(request: Request, error: Exception) -> JSONResponse:
    _ = request, error

    r = error_response(
        409,
        code="device_limit_reached",
        message="License device limit reached",
    )
    return r


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(HTTPException, handle_http_error)
    app.add_exception_handler(RequestValidationError, handle_validation_error)
    app.add_exception_handler(InvalidActivationRequestError, handle_validation_error)
    app.add_exception_handler(InvalidLicenseError, handle_invalid_license)
    app.add_exception_handler(DeviceLimitReachedError, handle_device_limit)
    app.add_exception_handler(Exception, handle_unexpected_error)
