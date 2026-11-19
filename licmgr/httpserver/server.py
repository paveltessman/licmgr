from pathlib import Path

from fastapi import FastAPI

from .api.router import router as api_router
from .error_handlers import register_exception_handlers
from .schemas import ErrorResponse
from .startup import lifespan
from licmgr.storage import DEFAULT_DB_PATH


def create_app(db_path: Path = Path(DEFAULT_DB_PATH)) -> FastAPI:
    app = FastAPI(
        title="License Manager API",
        lifespan=lifespan,
        redirect_slashes=False,
        responses={code: {"model": ErrorResponse} for code in (404, 405, 422, 500)},
    )
    app.state.db_path = db_path
    register_exception_handlers(app)
    app.include_router(api_router)
    return app
