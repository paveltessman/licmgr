from pathlib import Path
from typing import Annotated
from unittest.mock import create_autospec
from unittest.mock import patch

import pytest
from fastapi import Depends
from httpx import ASGITransport
from httpx import AsyncClient
from pydantic import ValidationError

from .dependencies import get_crypto_service
from .dependencies import get_license_service
from .schemas import SuccessResponse
from .server import create_app
from licmgr.services.crypto import CryptoService
from licmgr.services.license.service import LicenseService
from licmgr.storage import Db


@pytest.mark.usefixtures("server_private_key", "database_url")
async def test_lifespan_provides_services() -> None:
    app = create_app()

    @app.get("/test")
    def endpoint(
        service: Annotated[LicenseService, Depends(get_license_service)],
        crypto: Annotated[CryptoService, Depends(get_crypto_service)],
    ) -> SuccessResponse[int]:
        assert service is app.state.license_service
        assert isinstance(service, LicenseService)
        assert crypto is app.state.crypto_service
        assert isinstance(crypto, CryptoService)
        return SuccessResponse(data=3)

    async with app.router.lifespan_context(app):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/test")
            assert response.status_code == 200
            assert response.json() == {"data": 3, "error": None}

    assert not hasattr(app.state, "crypto_service")


@pytest.mark.usefixtures("server_private_key")
@pytest.mark.parametrize("startup_fails", [False, True])
async def test_lifespan_closes_database(
    monkeypatch: pytest.MonkeyPatch, startup_fails: bool
) -> None:
    app = create_app()
    database = create_autospec(Db, instance=True, spec_set=True)

    monkeypatch.setenv("LICMGR_DATABASE_URL", "postgresql://localhost/licmgr")
    with patch("licmgr.storage.db.Db", return_value=database):
        if startup_fails:
            database.initialize.side_effect = RuntimeError("startup failed")
            with pytest.raises(RuntimeError, match="startup failed"):
                async with app.router.lifespan_context(app):
                    pytest.fail("App started after database initialization failed")
        else:
            async with app.router.lifespan_context(app):
                database.close.assert_not_called()

    database.initialize.assert_called_once_with()
    database.close.assert_called_once_with()
    assert not hasattr(app.state, "license_service")


@pytest.mark.parametrize("key", [None, "invalid!"])
async def test_lifespan_requires_valid_private_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, key: str | None
) -> None:
    monkeypatch.chdir(tmp_path)
    if key is None:
        monkeypatch.delenv("LICMGR_SERVER_PRIVATE_KEY", raising=False)
    else:
        monkeypatch.setenv("LICMGR_SERVER_PRIVATE_KEY", key)
    app = create_app()

    with pytest.raises(ValidationError, match="LICMGR_SERVER_PRIVATE_KEY"):
        async with app.router.lifespan_context(app):
            pytest.fail("App started without a valid private key")


@pytest.mark.usefixtures("server_private_key", "database_url")
async def test_framework_errors_use_shared_response() -> None:
    app = create_app()

    @app.get("/test")
    def endpoint(count: int) -> None:
        raise RuntimeError("private error")

    async with app.router.lifespan_context(app):
        async with AsyncClient(
            transport=ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://test",
        ) as client:
            response = await client.get("/missing")
            assert response.status_code == 404
            assert response.json() == {
                "data": None,
                "error": {"code": "not_found", "message": "Not Found"},
            }

            response = await client.post("/test")
            assert response.status_code == 405
            assert response.headers["allow"] == "GET"
            assert response.json() == {
                "data": None,
                "error": {
                    "code": "method_not_allowed",
                    "message": "Method Not Allowed",
                },
            }

            response = await client.get("/test", params={"count": "invalid"})
            assert response.status_code == 422
            assert response.json() == {
                "data": None,
                "error": {
                    "code": "invalid_request",
                    "message": (
                        "Request validation failed: query.count: Input should be a "
                        "valid integer, unable to parse string as an integer"
                    ),
                },
            }

            response = await client.get("/test", params={"count": "1"})
            assert response.status_code == 500
            assert response.json() == {
                "data": None,
                "error": {"code": "internal_error", "message": "Internal server error"},
            }
