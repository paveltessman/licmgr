import base64
import json
from collections.abc import AsyncGenerator
from collections.abc import Callable
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
from cryptography.hazmat.primitives.hpke import AEAD
from cryptography.hazmat.primitives.hpke import KDF
from cryptography.hazmat.primitives.hpke import KEM
from cryptography.hazmat.primitives.hpke import Suite
from httpx import ASGITransport
from httpx import AsyncClient

from licmgr.httpserver.server import create_app
from licmgr.services.license import LicenseService
from licmgr.storage import LicenseRepo
from licmgr.storage import open_database

ACTIVATION_PATH = "/api/v1/licenses/activate/"
DEVICE_ID = "a" * 64
type Encrypt = Callable[[bytes], dict[str, int | str]]


@pytest.fixture
def encrypt(server_private_key: X25519PrivateKey) -> Encrypt:
    suite = Suite(KEM.X25519, KDF.HKDF_SHA256, AEAD.AES_128_GCM)
    public_key = server_private_key.public_key()

    def envelope(plaintext: bytes) -> dict[str, int | str]:
        ciphertext = suite.encrypt(plaintext, public_key, info=b"license-activation-v1")
        return {
            "version": 1,
            "ciphertext": base64.b64encode(ciphertext).decode("ascii"),
        }

    return envelope


@pytest.fixture
async def activation_client(
    tmp_path: Path, server_private_key: X25519PrivateKey
) -> AsyncGenerator[tuple[AsyncClient, str]]:
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
    encrypt: Encrypt,
) -> None:
    client, key = activation_client
    body = {"license_key": key, "device_id": DEVICE_ID}

    response = await client.post(
        ACTIVATION_PATH,
        json=encrypt(json.dumps(body).encode()),
    )
    assert response.status_code == 200
    assert response.json() == {"data": {"status": "activated"}, "error": None}

    response = await client.post(
        ACTIVATION_PATH,
        json=encrypt(json.dumps(body).encode()),
    )
    assert response.status_code == 200
    assert response.json() == {"data": {"status": "already_activated"}, "error": None}

    body["device_id"] = "b" * 64
    response = await client.post(
        ACTIVATION_PATH,
        json=encrypt(json.dumps(body).encode()),
    )
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
    encrypt: Encrypt,
) -> None:
    client, issued_key = activation_client
    unknown_key = "AAAA-BBBB-CCCC-DDDD"
    if issued_key == unknown_key:
        unknown_key = "EEEE-FFFF-GGGG-HHHH"

    body = {"license_key": unknown_key, "device_id": DEVICE_ID}
    response = await client.post(
        ACTIVATION_PATH,
        json=encrypt(json.dumps(body).encode()),
    )
    assert response.status_code == 404
    assert response.json() == {
        "data": None,
        "error": {"code": "invalid_license", "message": "License key is not valid"},
    }


@pytest.mark.parametrize(
    ("body", "details"),
    [
        (b"{", "Invalid encrypted payload"),
        (b"{}", "Invalid encrypted payload"),
        (
            b'{"license_key":123,"device_id":"invalid"}',
            "Invalid encrypted payload",
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
    activation_client: tuple[AsyncClient, str],
    encrypt: Encrypt,
    body: bytes,
    details: str,
) -> None:
    client, _ = activation_client
    response = await client.post(ACTIVATION_PATH, json=encrypt(body))
    assert response.status_code == 422
    assert response.json() == {
        "data": None,
        "error": {
            "code": "invalid_request",
            "message": f"Request validation failed: {details}",
        },
    }


@pytest.mark.parametrize(
    "body",
    [
        b"{",
        b"{}",
        b'{"license_key":"AAAA-BBBB-CCCC-DDDD","device_id":"invalid"}',
        b'{"version":2,"ciphertext":"AA=="}',
        b'{"version":true,"ciphertext":"AA=="}',
        b'{"version":"1","ciphertext":"AA=="}',
        b'{"version":1,"ciphertext":"AA"}',
        b'{"version":1,"ciphertext":"!!=="}',
        b'{"version":1,"ciphertext":""}',
        b'{"version":1,"ciphertext":"AA=="}',
    ],
)
async def test_activate_rejects_invalid_envelopes(
    activation_client: tuple[AsyncClient, str], body: bytes
) -> None:
    client, _ = activation_client
    response = await client.post(
        ACTIVATION_PATH, content=body, headers={"Content-Type": "application/json"}
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_request"


@pytest.mark.parametrize("path", ["/activate", ACTIVATION_PATH.rstrip("/")])
async def test_activation_requires_exact_path(
    activation_client: tuple[AsyncClient, str], path: str
) -> None:
    client, key = activation_client
    response = await client.post(
        path, json={"license_key": key, "device_id": DEVICE_ID}
    )
    assert response.status_code == 404
