from collections.abc import AsyncGenerator
from pathlib import Path

import pytest
from httpx import ASGITransport
from httpx import AsyncClient

from licmgr.httpserver.server import create_app
from licmgr.services.license import LicenseService
from licmgr.storage import LicenseRepo
from licmgr.storage import open_database

ACTIVATION_PATH = "/api/v1/licenses/activate/"
DEVICE_ID = "a" * 64


@pytest.fixture
async def activation_client(tmp_path: Path) -> AsyncGenerator[tuple[AsyncClient, str]]:
    db_path = tmp_path / "licenses.sqlite3"
    with open_database(db_path) as database:
        key = LicenseService(LicenseRepo(database)).create_license(max_devices=1)

    app = create_app(db_path)
    async with app.router.lifespan_context(app):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            yield client, key


async def test_activate_at_device_limit(
    activation_client: tuple[AsyncClient, str],
) -> None:
    client, key = activation_client
    body = {"license_key": key, "device_id": DEVICE_ID}

    response = await client.post(ACTIVATION_PATH, json=body)
    assert response.status_code == 200
    assert response.json() == {"data": {"status": "activated"}, "error": None}

    response = await client.post(ACTIVATION_PATH, json=body)
    assert response.status_code == 200
    assert response.json() == {"data": {"status": "already_activated"}, "error": None}

    response = await client.post(ACTIVATION_PATH, json={**body, "device_id": "b" * 64})
    assert response.status_code == 409
    assert response.json() == {
        "data": None,
        "error": {
            "code": "device_limit_reached",
            "message": "License device limit reached",
        },
    }


async def test_activate_rejects_unissued_key(
    activation_client: tuple[AsyncClient, str],
) -> None:
    client, issued_key = activation_client
    unknown_key = "AAAA-BBBB-CCCC-DDDD"
    if issued_key == unknown_key:
        unknown_key = "EEEE-FFFF-GGGG-HHHH"

    response = await client.post(
        ACTIVATION_PATH, json={"license_key": unknown_key, "device_id": DEVICE_ID}
    )
    assert response.status_code == 404
    assert response.json() == {
        "data": None,
        "error": {"code": "invalid_license", "message": "License key is not valid"},
    }


@pytest.mark.parametrize(
    ("body", "details"),
    [
        (b"{", "body.1: JSON decode error"),
        (b"{}", "body.license_key: Field required; body.device_id: Field required"),
        (
            b'{"license_key":123,"device_id":"invalid"}',
            "body.license_key: Input should be a valid string",
        ),
        (
            b'{"license_key":"short","device_id":"' + DEVICE_ID.encode() + b'"}',
            "Invalid license key format",
        ),
        (
            b'{"license_key":"AAAA-BBBB-CCCC-DDDD","device_id":"invalid"}',
            "Invalid device ID format",
        ),
    ],
)
async def test_activate_rejects_invalid_requests(
    activation_client: tuple[AsyncClient, str], body: bytes, details: str
) -> None:
    client, _ = activation_client
    response = await client.post(
        ACTIVATION_PATH, content=body, headers={"Content-Type": "application/json"}
    )
    assert response.status_code == 422
    assert response.json() == {
        "data": None,
        "error": {
            "code": "invalid_request",
            "message": f"Request validation failed: {details}",
        },
    }


@pytest.mark.parametrize("path", ["/activate", ACTIVATION_PATH.rstrip("/")])
async def test_activation_requires_exact_path(
    activation_client: tuple[AsyncClient, str], path: str
) -> None:
    client, key = activation_client
    response = await client.post(
        path, json={"license_key": key, "device_id": DEVICE_ID}
    )
    assert response.status_code == 404
