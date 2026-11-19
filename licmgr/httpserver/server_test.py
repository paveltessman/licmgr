from pathlib import Path
from typing import Annotated
from unittest.mock import create_autospec
from unittest.mock import patch

import pytest
from fastapi import Depends
from httpx import ASGITransport
from httpx import AsyncClient

from .dependencies import get_license_service
from .schemas import SuccessResponse
from .server import create_app
from licmgr.services.license.service import LicenseService
from licmgr.storage import Db


async def test_lifespan_provides_service(tmp_path: Path) -> None:
    db_path = tmp_path / "licenses.sqlite3"
    app = create_app(db_path)

    @app.get("/test")
    def endpoint(
        service: Annotated[LicenseService, Depends(get_license_service)],
    ) -> SuccessResponse[int]:
        assert service is app.state.license_service
        assert isinstance(service, LicenseService)
        return SuccessResponse(data=3)

    async with app.router.lifespan_context(app):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/test")
            assert response.status_code == 200
            assert response.json() == {"data": 3, "error": None}

    assert db_path.is_file()


@pytest.mark.parametrize("startup_fails", [False, True])
async def test_lifespan_closes_database(tmp_path: Path, startup_fails: bool) -> None:
    app = create_app(tmp_path / "licenses.sqlite3")
    database = create_autospec(Db, instance=True, spec_set=True)

    with patch.object(Db, "from_sqlite_path", return_value=database):
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


async def test_framework_errors_use_shared_response(tmp_path: Path) -> None:
    app = create_app(tmp_path / "licenses.sqlite3")

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
                    "message": "Request validation failed",
                },
            }

            response = await client.get("/test", params={"count": "1"})
            assert response.status_code == 500
            assert response.json() == {
                "data": None,
                "error": {"code": "internal_error", "message": "Internal server error"},
            }
