from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI

from licmgr.services.license import LicenseService
from licmgr.storage import LicenseRepo
from licmgr.storage import open_database


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    db_path: Path = app.state.db_path

    with open_database(db_path) as database:
        app.state.license_service = LicenseService(LicenseRepo(database))
        yield
