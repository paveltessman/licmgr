from fastapi import FastAPI

from .api.router import router as api_router
from .error_handlers import register_exception_handlers
from .middleware import ActivationErrorLoggingMiddleware
from .schemas import ErrorResponse
from .startup import lifespan


def create_app() -> FastAPI:
    app = FastAPI(
        title="License Manager API",
        lifespan=lifespan,
        redirect_slashes=False,
        responses={code: {"model": ErrorResponse} for code in (404, 405, 422, 500)},
    )
    app.add_middleware(ActivationErrorLoggingMiddleware)
    register_exception_handlers(app)
    app.include_router(api_router)
    return app
