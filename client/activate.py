import argparse
import base64
import hmac
import json
import os
import platform
import re
import sys
from http import HTTPStatus
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

NETWORK_INTERFACES_PATH = Path("/sys/class/net")
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
    (404, "not_found"): "Activation endpoint not found",
    (409, "device_limit_reached"): "License device limit reached",
    (422, "invalid_request"): "Invalid activation request",
}


class ActivationError(Exception):
    """The client could not complete activation."""


def validate_license_key(license_key: str) -> None:
    if re.fullmatch(r"[A-Z0-9]{4}(?:-[A-Z0-9]{4}){3}", license_key) is None:
        raise ActivationError(
            "invalid license key format: expected four groups of four uppercase "
            "letters or digits separated by hyphens (XXXX-XXXX-XXXX-XXXX)"
        )


def read_mac_address(interface: Path) -> str | None:
    if interface.name == "lo":
        return None

    try:
        address = (interface / "address").read_text(encoding="ascii").strip().lower()
    except (OSError, UnicodeError):
        return None

    if (
        re.fullmatch(r"[0-9a-f]{2}(?::[0-9a-f]{2}){5}", address)
        and address != "00:00:00:00:00:00"
        and int(address[:2], 16) % 2 == 0
    ):
        return address

    return None


def get_mac_address() -> str:
    try:
        interfaces = list(NETWORK_INTERFACES_PATH.iterdir())
    except OSError as error:
        raise ActivationError(
            f"could not list Linux network interfaces: {error}"
        ) from error

    addresses = (read_mac_address(interface) for interface in interfaces)
    selected = min(
        (address for address in addresses if address is not None), default=None
    )
    if selected is None:
        raise ActivationError("could not find a usable MAC address")

    return selected


def get_device_id(*, print_details: bool = False) -> str:
    os_version = platform.release()
    architecture = platform.machine()
    core_count = os.cpu_count()
    if not os_version or not architecture or core_count is None or core_count < 1:
        raise ActivationError("could not determine Linux kernel release or CPU details")

    mac_address = get_mac_address()
    fingerprint = json.dumps(
        [os_version, architecture, core_count, mac_address], separators=(",", ":")
    ).encode("utf-8")
    device_id = hmac.digest(b"licmgr/device-id/v2", fingerprint, "sha256").hex()
    if print_details:
        print(
            f"OS version (Linux kernel): {os_version}\n"
            f"CPU architecture: {architecture}\n"
            f"Logical CPU count: {core_count}\n"
            f"MAC address: {mac_address}\n"
            f"Device ID: {device_id}",
            flush=True,
        )
    return device_id


def response_field(payload: object, name: str) -> object:
    if isinstance(payload, dict):
        return cast(dict[str, object], payload).get(name)
    return None


def rejection_message(status: int, payload: object) -> str:
    error = response_field(payload, "error")
    code = response_field(error, "code")
    message = response_field(error, "message")

    if (
        400 <= status < 600
        and response_field(payload, "data") is None
        and isinstance(code, str)
        and code.strip()
        and (message is None or isinstance(message, str))
    ):
        detail = ERROR_MESSAGES.get((status, code), "Activation request failed")
        if (status, code) != (404, "not_found") and message and message.strip():
            detail = message.strip()
        return f"{detail} (HTTP {status}, {code})"

    if status == HTTPStatus.NOT_FOUND:
        return "Activation request failed (HTTP 404 Not Found)"

    return f"Unexpected activation response (HTTP {status})"


def parse_response(status: int, body: bytes) -> object:
    try:
        return cast(object, json.loads(body))
    except (ValueError, RecursionError) as error:
        if status != HTTPStatus.OK:
            raise ActivationError(rejection_message(status, None)) from error
        raise ActivationError(
            f"invalid activation response (HTTP {status}): {error}"
        ) from error


def response_message(status: int, body: bytes) -> str:
    payload = parse_response(status, body)
    if status == HTTPStatus.OK and response_field(payload, "error") is None:
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
        raise ActivationError(f"set {SERVER_PUBLIC_KEY_ENV} to the server public key")

    try:
        key = base64.b64decode(value, validate=True)
        if base64.b64encode(key).decode("ascii") == value:
            return X25519PublicKey.from_public_bytes(key)
    except (ValueError, UnsupportedAlgorithm):
        pass

    raise ActivationError(
        f"invalid {SERVER_PUBLIC_KEY_ENV}: expected a 32-byte X25519 public key "
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
        raise ActivationError("could not encrypt the activation request") from error

    return json.dumps(
        {"version": 1, "ciphertext": base64.b64encode(ciphertext).decode("ascii")}
    )


def activate(
    server_url: str,
    license_key: str,
    device_id: str,
    public_key: X25519PublicKey,
) -> str:
    validate_license_key(license_key)
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
        raise ActivationError(f"invalid server URL: {error}") from error

    except (OSError, HTTPException) as error:
        detail = str(error) or type(error).__name__
        message = (
            f"activation request timed out (socket timeout: {REQUEST_TIMEOUT} seconds)"
            if isinstance(error, TimeoutError)
            else f"could not complete the activation request: {detail}"
        )
        raise ActivationError(message) from error

    return response_message(status, body)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Activate a license on a Linux installation."
    )
    parser.add_argument("license_key", help="License key as issued by the server")
    parser.add_argument(
        "--server-url",
        default="http://127.0.0.1:8000",
        help="Activation server base URL",
    )
    args = parser.parse_args(argv)

    try:
        validate_license_key(args.license_key)
        message = activate(
            args.server_url,
            args.license_key,
            get_device_id(print_details=True),
            load_server_public_key(),
        )
    except ActivationError as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1

    print(message)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
