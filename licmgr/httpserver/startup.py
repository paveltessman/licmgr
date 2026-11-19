from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
from fastapi import FastAPI

from licmgr.services.crypto import CryptoService
from licmgr.services.license import LicenseService
from licmgr.settings import Settings
from licmgr.storage import LicenseRepo
from licmgr.storage import open_database


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    db_path: Path = app.state.db_path
    settings = Settings()
    key = X25519PrivateKey.from_private_bytes(
        settings.LICMGR_SERVER_PRIVATE_KEY.get_secret_value()
    )
    crypto_service = CryptoService(key)

    with open_database(db_path) as database:
        app.state.license_service = LicenseService(LicenseRepo(database))
        app.state.crypto_service = crypto_service
        try:
            yield
        finally:
            del app.state.crypto_service
            del app.state.license_service
