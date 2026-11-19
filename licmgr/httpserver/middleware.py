from starlette.types import ASGIApp
from starlette.types import Message
from starlette.types import Receive
from starlette.types import Scope
from starlette.types import Send

from .api.v1.licenses.licenses import activate
from .api.v1.licenses.licenses import activation_logger
from .error_handlers import error_response


_ERROR_DETAILS = {
    404: "Invalid license key",
    409: "License device limit reached",
    422: "Invalid activation request",
}


def _log_failed_activation(scope: Scope, message: Message) -> None:
    if (
        message["type"] == "http.response.start"
        and scope.get("endpoint") is activate
        and message["status"] >= 400
    ):
        status = message["status"]
        activation_logger.info(
            "Activation outcome=error status=%d detail=%s",
            status,
            _ERROR_DETAILS.get(status, "Activation request failed"),
        )


class ActivationErrorLoggingMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        response_started = False

        async def log_response(message: Message) -> None:
            nonlocal response_started
            response_started = (
                response_started or message["type"] == "http.response.start"
            )
            _log_failed_activation(scope, message)
            await send(message)

        try:
            await self.app(scope, receive, log_response)
        except Exception as error:
            if scope.get("endpoint") is not activate or response_started:
                raise
            # Handle the error here so the ASGI server cannot log its traceback.
            activation_logger.error(
                "Activation outcome=error status=500 detail=Internal server error "
                "exception_type=%s",
                type(error).__name__,
            )
            response = error_response(
                500, code="internal_error", message="Internal server error"
            )
            await response(scope, receive, send)
