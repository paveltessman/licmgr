import re
import sqlite3
from contextlib import closing
from pathlib import Path

import pytest
from click.testing import CliRunner

from .cli import cli


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
