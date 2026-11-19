import base64
import json
from pathlib import Path
from typing import cast
from unittest.mock import patch

import activate
import pytest
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
from cryptography.hazmat.primitives.hpke import AEAD
from cryptography.hazmat.primitives.hpke import KDF
from cryptography.hazmat.primitives.hpke import KEM
from cryptography.hazmat.primitives.hpke import Suite

LICENSE_KEY = "ABCD-EFGH-IJKL-MNOP"
DEVICE_ID = "5e8258ad339c5da15abd4122e24e734c1473c8efe736f541e0bd786a004ad48f"


@pytest.fixture
def server_private_key(monkeypatch: pytest.MonkeyPatch) -> X25519PrivateKey:
    key = X25519PrivateKey.generate()
    public_bytes = key.public_key().public_bytes_raw()
    monkeypatch.setenv(
        "LICMGR_SERVER_PUBLIC_KEY", base64.b64encode(public_bytes).decode("ascii")
    )
    return key


@pytest.fixture
def network_interfaces(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(activate, "NETWORK_INTERFACES_PATH", tmp_path)
    monkeypatch.setattr(activate.platform, "release", lambda: "6.12.0")
    monkeypatch.setattr(activate.platform, "machine", lambda: "x86_64")
    monkeypatch.setattr(activate.os, "cpu_count", lambda: 8)
    for name, value in (
        ("eth0", "02:00:00:00:00:02"),
        ("eth1", "02:00:00:00:00:01"),
        ("lo", "00:00:00:00:00:01"),
    ):
        interface = tmp_path / name
        interface.mkdir()
        (interface / "address").write_text(f" {value}\n", encoding="ascii")
    return tmp_path


@pytest.mark.parametrize(
    ("status", "payload", "exit_code", "message"),
    [
        (200, {"data": {"status": "activated"}}, 0, "Activated"),
        (200, {"data": {"status": "already_activated"}}, 0, "Already activated"),
        (
            404,
            {"error": {"code": "invalid_license"}},
            1,
            "License key is not valid (HTTP 404, invalid_license)",
        ),
        (
            409,
            {"error": {"code": "device_limit_reached"}},
            1,
            "License device limit reached (HTTP 409, device_limit_reached)",
        ),
        (
            422,
            {
                "error": {
                    "code": "invalid_request",
                    "message": "Request validation failed: Invalid license key format",
                }
            },
            1,
            "Request validation failed: Invalid license key format "
            "(HTTP 422, invalid_request)",
        ),
        (
            500,
            {"error": {"code": "internal_error", "message": "Internal server error"}},
            1,
            "Internal server error (HTTP 500, internal_error)",
        ),
        (502, {"error": {}}, 1, "Unexpected activation response (HTTP 502)"),
        (
            200,
            {"data": {"status": "unknown"}},
            1,
            "Unexpected activation response (HTTP 200)",
        ),
    ],
)
def test_activation(
    network_interfaces: Path,
    server_private_key: X25519PrivateKey,
    capsys: pytest.CaptureFixture[str],
    status: int,
    payload: dict[str, object],
    exit_code: int,
    message: str,
) -> None:
    with patch.object(activate, "HTTPConnection", autospec=True) as connect:
        connection = connect.return_value
        response = connection.getresponse.return_value.__enter__.return_value
        response.status = status
        response.read.return_value = json.dumps(payload).encode()

        assert activate.main([LICENSE_KEY]) == exit_code

        connect.assert_called_once_with("127.0.0.1", 8000, timeout=10)
        request_body: object = connection.request.call_args.kwargs["body"]
        assert isinstance(request_body, str)
        envelope = cast(dict[str, object], json.loads(request_body))
        assert isinstance(envelope, dict)
        assert set(envelope) == {"version", "ciphertext"}
        assert type(envelope["version"]) is int and envelope["version"] == 1
        encoded = envelope["ciphertext"]
        assert isinstance(encoded, str)
        ciphertext = base64.b64decode(encoded, validate=True)
        assert base64.b64encode(ciphertext).decode("ascii") == encoded
        suite = Suite(KEM.X25519, KDF.HKDF_SHA256, AEAD.AES_128_GCM)
        plaintext = suite.decrypt(
            ciphertext, server_private_key, info=b"license-activation-v1"
        )
        assert json.loads(plaintext) == {
            "license_key": LICENSE_KEY,
            "device_id": DEVICE_ID,
        }
        connection.request.assert_called_once_with(
            "POST",
            "/api/v1/licenses/activate/",
            body=request_body,
            headers={"Content-Type": "application/json"},
        )
        connection.close.assert_called_once_with()

    captured = capsys.readouterr()
    details = (
        "OS version (Linux kernel): 6.12.0\n"
        "CPU architecture: x86_64\n"
        "Logical CPU count: 8\n"
        "MAC address: 02:00:00:00:00:01\n"
        f"Device ID: {DEVICE_ID}\n"
    )
    if exit_code:
        assert captured.err == f"Error: {message}\n"
        assert captured.out == details
    else:
        assert captured.out == f"{details}{message}\n"
        assert captured.err == ""


@pytest.mark.parametrize(
    "value", [b"1234", b"00:00:00:00:00:00", b"01:00:00:00:00:00", b"\xff", None]
)
def test_unusable_mac_address(
    network_interfaces: Path, capsys: pytest.CaptureFixture[str], value: bytes | None
) -> None:
    for name in ("eth0", "eth1"):
        address = network_interfaces / name / "address"
        if value is None:
            address.unlink()
        else:
            address.write_bytes(value)

    with patch.object(activate, "HTTPConnection", autospec=True) as connect:
        assert activate.main([LICENSE_KEY]) == 1
        connect.assert_not_called()

    assert "usable MAC address" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("error", "detail"),
    [
        (ConnectionRefusedError("Connection refused"), "Connection refused"),
        (TimeoutError(), "activation request timed out (socket timeout: 10 seconds)"),
    ],
)
def test_transport_failure(
    network_interfaces: Path,
    server_private_key: X25519PrivateKey,
    capsys: pytest.CaptureFixture[str],
    error: OSError,
    detail: str,
) -> None:
    with patch.object(activate, "HTTPSConnection", autospec=True) as connect:
        connect.return_value.request.side_effect = error

        assert activate.main(["--server-url", "https://example.test", LICENSE_KEY]) == 1

        connect.assert_called_once_with("example.test", None, timeout=10)
        connect.return_value.close.assert_called_once_with()

    assert detail in capsys.readouterr().err


@pytest.mark.parametrize(
    ("value", "detail"),
    [
        (None, "set LICMGR_SERVER_PUBLIC_KEY"),
        ("not-base64", "invalid LICMGR_SERVER_PUBLIC_KEY"),
        ("YQ==", "invalid LICMGR_SERVER_PUBLIC_KEY"),
        ("A" * 43, "invalid LICMGR_SERVER_PUBLIC_KEY"),
        ("A" * 42 + "B=", "invalid LICMGR_SERVER_PUBLIC_KEY"),
        ("A" * 43 + "=", "could not encrypt the activation request"),
    ],
)
def test_unusable_server_public_key(
    network_interfaces: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    value: str | None,
    detail: str,
) -> None:
    if value is None:
        monkeypatch.delenv("LICMGR_SERVER_PUBLIC_KEY", raising=False)
    else:
        monkeypatch.setenv("LICMGR_SERVER_PUBLIC_KEY", value)

    with patch.object(activate, "HTTPConnection", autospec=True) as connect:
        assert activate.main([LICENSE_KEY]) == 1
        connect.assert_not_called()

    assert detail in capsys.readouterr().err


def test_malformed_response() -> None:
    with pytest.raises(
        activate.ActivationError, match=r"invalid activation response \(HTTP 200\): .+"
    ):
        activate.response_message(200, b"{")


@pytest.mark.parametrize(
    "key",
    ["", "abcd-EFGH-IJKL-MNOP", "ABC-EFGH-IJKL-MNOP", "ABCD-EFGH-IJKL-MNOP\n"],
)
def test_invalid_license_key(key: str, capsys: pytest.CaptureFixture[str]) -> None:
    with patch.object(activate, "get_device_id", autospec=True) as get_device_id:
        assert activate.main([key]) == 1
        get_device_id.assert_not_called()

    assert "invalid license key format" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("status", "body", "message"),
    [
        (404, b"<html>Not Found</html>", "HTTP 404 Not Found"),
        (404, b'{"detail":"Not Found"}', "HTTP 404 Not Found"),
        (
            404,
            b'{"error":{"code":"not_found","message":"Not Found"}}',
            "Activation endpoint not found",
        ),
        (503, b"", "Unexpected activation response"),
        (200, b'{"data":[]}', "Unexpected activation response"),
        (
            200,
            b'{"data":{"status":"activated"},"error":{"code":"unexpected"}}',
            "Unexpected activation response",
        ),
        (
            409,
            b'{"error":{"code":"device_limit_reached","message":[]}}',
            "Unexpected activation response",
        ),
    ],
)
def test_unexpected_response(status: int, body: bytes, message: str) -> None:
    with pytest.raises(activate.ActivationError, match=message):
        activate.response_message(status, body)
