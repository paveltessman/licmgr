import base64
import re
from pathlib import Path
from uuid import uuid4

import pytest
from click.testing import CliRunner
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
from sqlalchemy import select
from sqlalchemy.engine import URL

from .cli import cli
from licmgr.storage import open_database
from licmgr.storage.licenses import License


def test_generate_keypair_prints_matching_activation_keys() -> None:
    result = CliRunner().invoke(cli, ["keypair"])

    assert result.exit_code == 0, result.output
    assert result.stderr == ""
    private_line, public_line = result.stdout.splitlines()
    private_name, _, private_value = private_line.partition("=")
    public_name, _, public_value = public_line.partition("=")
    assert private_name == "LICMGR_SERVER_PRIVATE_KEY"
    assert public_name == "LICMGR_SERVER_PUBLIC_KEY"

    private_bytes = base64.b64decode(private_value, validate=True)
    public_bytes = base64.b64decode(public_value, validate=True)
    assert base64.b64encode(private_bytes).decode("ascii") == private_value
    assert base64.b64encode(public_bytes).decode("ascii") == public_value
    private_key = X25519PrivateKey.from_private_bytes(private_bytes)
    assert private_key.public_key().public_bytes_raw() == public_bytes


@pytest.mark.parametrize(
    ("options", "max_devices"),
    [
        ([], 1),
        (["--max-devices", "3"], 3),
    ],
)
def test_create_persists_printed_key(
    database_url: URL, options: list[str], max_devices: int
) -> None:
    result = CliRunner().invoke(cli, ["keys", "create", *options])

    assert result.exit_code == 0, result.output
    assert re.fullmatch(r"[A-Z0-9]{4}(?:-[A-Z0-9]{4}){3}\n", result.stdout)
    assert result.stderr == ""

    with open_database(database_url) as database, database.transaction() as session:
        license = session.scalars(select(License)).one()
        assert license.key == result.stdout.strip()
        assert license.max_devices == max_devices


@pytest.mark.parametrize("value", ["0", "-1", "abc"])
def test_create_rejects_invalid_device_limits(value: str) -> None:
    result = CliRunner().invoke(cli, ["keys", "create", "--max-devices", value])

    assert result.exit_code == 2
    assert result.stdout == ""
    assert "Invalid value for '--max-devices'" in result.stderr


def test_create_requires_database_url(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("LICMGR_DATABASE_URL", raising=False)

    result = CliRunner().invoke(cli, ["keys", "create"])

    assert result.exit_code == 1
    assert result.stdout == ""
    assert "Set LICMGR_DATABASE_URL" in result.stderr


def test_create_reports_database_failure(
    database_url: URL, monkeypatch: pytest.MonkeyPatch
) -> None:
    url = database_url.set(database=f"missing_{uuid4().hex}")
    monkeypatch.setenv("LICMGR_DATABASE_URL", url.render_as_string(hide_password=False))
    result = CliRunner().invoke(cli, ["keys", "create"])

    assert result.exit_code == 1
    assert result.stdout == ""
    assert result.stderr == "Error: Database operation failed\n"
