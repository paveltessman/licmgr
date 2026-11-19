import argparse
import base64
import hmac
import json
import os
import re
import sys
from http.client import HTTPConnection
from http.client import HTTPException
from http.client import HTTPSConnection
from pathlib import Path
from typing import cast
from urllib.parse import urlsplit

from cryptography.exceptions import UnsupportedAlgorithm
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PublicKey
from cryptography.hazmat.primitives.hpke import AEAD
from cryptography.hazmat.primitives.hpke import KDF
from cryptography.hazmat.primitives.hpke import KEM
from cryptography.hazmat.primitives.hpke import Suite

MACHINE_ID_PATH = Path("/etc/machine-id")
ACTIVATION_PATH = "/api/v1/licenses/activate/"
REQUEST_TIMEOUT = 10
ACTIVATION_INFO = b"license-activation-v1"
SERVER_PUBLIC_KEY_ENV = "LICMGR_SERVER_PUBLIC_KEY"

SUCCESS_MESSAGES = {
    "activated": "Activated",
    "already_activated": "Already activated",
}
ERROR_MESSAGES = {
    (404, "invalid_license"): "License key is not valid",
    (409, "device_limit_reached"): "License device limit reached",
    (422, "invalid_request"): "Invalid activation request",
}


class ActivationError(Exception):
    """The client could not complete activation."""


def get_device_id() -> str:
    try:
        machine_id = MACHINE_ID_PATH.read_text(encoding="ascii").strip()
    except (OSError, UnicodeError) as error:
        raise ActivationError(
            f"Could not read the Linux machine ID: {error}"
        ) from error

    if not re.fullmatch(r"[0-9a-f]{32}", machine_id) or machine_id == "0" * 32:
        raise ActivationError(
            "Invalid Linux machine ID: expected 32 lowercase hexadecimal digits, "
            "with at least one nonzero digit"
        )
    h = hmac.digest(b"licmgr/device-id/v1", bytes.fromhex(machine_id), "sha256").hex()
    return h


def response_field(payload: object, name: str) -> object:
    if isinstance(payload, dict):
        return cast(dict[str, object], payload).get(name)
    return None


def rejection_message(status: int, payload: object) -> str:

    error = response_field(payload, "error")
    code = response_field(error, "code")
    message = response_field(error, "message")

    if status != 200 and isinstance(code, str) and code:
        detail = ERROR_MESSAGES.get((status, code), "Activation request failed")
        if isinstance(message, str) and message.strip():
            detail = message.strip()
        return f"{detail} (HTTP {status}, {code})"

    return f"Unexpected activation response (HTTP {status})"


def response_message(status: int, body: bytes) -> str:

    try:
        payload: object = json.loads(body)
    except (ValueError, RecursionError) as error:
        raise ActivationError(
            f"Invalid activation response (HTTP {status}): {error}"
        ) from error

    if status == 200:
        result = response_field(response_field(payload, "data"), "status")
        if isinstance(result, str) and result in SUCCESS_MESSAGES:
            return SUCCESS_MESSAGES[result]

    raise ActivationError(rejection_message(status, payload))


def server_connection(server_url: str) -> tuple[HTTPConnection, str]:
    url = urlsplit(server_url)

    if url.scheme not in ("http", "https") or not url.hostname:
        raise ValueError("Expected an HTTP or HTTPS URL")

    connection_type = HTTPSConnection if url.scheme == "https" else HTTPConnection
    connection = connection_type(url.hostname, url.port, timeout=REQUEST_TIMEOUT)

    return connection, url.path.rstrip("/") + ACTIVATION_PATH


def load_server_public_key() -> X25519PublicKey:
    value = os.environ.get(SERVER_PUBLIC_KEY_ENV)
    if value is None:
        raise ActivationError(f"Set {SERVER_PUBLIC_KEY_ENV} to the server public key")

    try:
        key = base64.b64decode(value, validate=True)
        if base64.b64encode(key).decode("ascii") == value:
            return X25519PublicKey.from_public_bytes(key)
    except (ValueError, UnsupportedAlgorithm):
        pass

    raise ActivationError(
        f"Invalid {SERVER_PUBLIC_KEY_ENV}: expected a 32-byte X25519 public key "
        "in standard padded base64"
    )


def encrypt_request(
    license_key: str,
    device_id: str,
    public_key: X25519PublicKey,
) -> str:
    plaintext = json.dumps({"license_key": license_key, "device_id": device_id}).encode(
        "utf-8"
    )
    try:
        suite = Suite(KEM.X25519, KDF.HKDF_SHA256, AEAD.AES_128_GCM)
        ciphertext = suite.encrypt(plaintext, public_key, info=ACTIVATION_INFO)
    except (ValueError, UnsupportedAlgorithm) as error:
        raise ActivationError("Could not encrypt the activation request") from error

    return json.dumps(
        {"version": 1, "ciphertext": base64.b64encode(ciphertext).decode("ascii")}
    )


def activate(
    server_url: str,
    license_key: str,
    device_id: str,
    public_key: X25519PublicKey,
) -> str:
    envelope = encrypt_request(license_key, device_id, public_key)
    try:
        connection, path = server_connection(server_url)

        try:
            connection.request(
                "POST",
                path,
                body=envelope,
                headers={"Content-Type": "application/json"},
            )

            with connection.getresponse() as response:
                status, body = response.status, response.read()

        finally:
            connection.close()

    except ValueError as error:
        raise ActivationError(f"Invalid server URL: {error}") from error

    except (OSError, HTTPException) as error:
        detail = str(error) or type(error).__name__
        message = (
            f"Activation request timed out (socket timeout: {REQUEST_TIMEOUT} seconds)"
            if isinstance(error, TimeoutError)
            else f"Could not complete the activation request: {detail}"
        )
        raise ActivationError(message) from error

    return response_message(status, body)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Activate a license on this Linux installation."
    )
    parser.add_argument("license_key", help="License key as issued by the server")
    parser.add_argument(
        "--server-url",
        default="http://127.0.0.1:8000",
        help="Activation server base URL",
    )
    args = parser.parse_args(argv)

    try:
        message = activate(
            args.server_url,
            args.license_key,
            get_device_id(),
            load_server_public_key(),
        )
    except ActivationError as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1

    print(message)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
