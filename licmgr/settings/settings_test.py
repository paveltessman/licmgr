import base64
from pathlib import Path

import pytest
from pydantic import ValidationError

from .settings import Settings

KEY_ENV = "LICMGR_SERVER_PRIVATE_KEY"
KEY = bytes(range(32))
ENCODED_KEY = base64.b64encode(KEY).decode("ascii")


@pytest.fixture(autouse=True)
def isolated_environment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv(KEY_ENV, raising=False)


def test_loads_private_key_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(KEY_ENV, ENCODED_KEY)
    settings = Settings()

    assert settings.LICMGR_SERVER_PRIVATE_KEY.get_secret_value() == KEY
    assert ENCODED_KEY not in repr(settings)
    assert settings.model_dump(mode="json")[KEY_ENV] == "**********"


def test_environment_overrides_dotenv(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    (tmp_path / ".env").write_text(f"{KEY_ENV}={ENCODED_KEY}\n", encoding="utf-8")
    assert Settings().LICMGR_SERVER_PRIVATE_KEY.get_secret_value() == KEY

    other_key = b"x" * 32
    monkeypatch.setenv(KEY_ENV, base64.b64encode(other_key).decode("ascii"))
    assert Settings().LICMGR_SERVER_PRIVATE_KEY.get_secret_value() == other_key


def test_requires_private_key() -> None:
    with pytest.raises(ValidationError) as exc_info:
        Settings()

    issue = exc_info.value.errors(include_input=False)[0]
    assert issue["loc"] == (KEY_ENV,)
    assert issue["type"] == "missing"


@pytest.mark.parametrize("value", ["invalid!", "eA==", ENCODED_KEY.rstrip("=")])
def test_rejects_invalid_private_key(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    monkeypatch.setenv(KEY_ENV, value)

    with pytest.raises(ValidationError, match="32-byte X25519 private key") as exc_info:
        Settings()

    assert value not in str(exc_info.value)
