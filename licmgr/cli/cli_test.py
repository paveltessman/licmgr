import base64
import re
import sqlite3
from contextlib import closing
from pathlib import Path

import pytest
from click.testing import CliRunner
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey

from .cli import cli


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
    ("options", "filename", "max_devices"),
    [
        ([], "db.sqlite3", 1),
        (["--db", "demo.sqlite3", "--max-devices", "3"], "demo.sqlite3", 3),
    ],
)
def test_create_persists_printed_key(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    options: list[str],
    filename: str,
    max_devices: int,
) -> None:
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(cli, ["keys", "create", *options])

    assert result.exit_code == 0, result.output
    assert re.fullmatch(r"[A-Z0-9]{4}(?:-[A-Z0-9]{4}){3}\n", result.stdout)
    assert result.stderr == ""

    with closing(sqlite3.connect(tmp_path / filename)) as connection:
        rows = connection.execute("SELECT key, max_devices FROM licenses").fetchall()
    assert rows == [(result.stdout.rstrip("\n"), max_devices)]


@pytest.mark.parametrize("value", ["0", "-1", "abc", str(2**63)])
def test_create_rejects_invalid_device_limits(tmp_path: Path, value: str) -> None:
    db_path = tmp_path / "licenses.sqlite3"
    result = CliRunner().invoke(
        cli, ["keys", "create", "--db", str(db_path), "--max-devices", value]
    )

    assert result.exit_code == 2
    assert result.stdout == ""
    assert "Invalid value for '--max-devices'" in result.stderr
    assert not db_path.exists()


def test_create_reports_database_failure(tmp_path: Path) -> None:
    db_path = tmp_path / "missing" / "licenses.sqlite3"
    result = CliRunner().invoke(cli, ["keys", "create", "--db", str(db_path)])

    assert result.exit_code == 1
    assert result.stdout == ""
    assert result.stderr == "Error: Database operation failed\n"
