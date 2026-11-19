import base64
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey


@pytest.fixture
def server_private_key(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> X25519PrivateKey:
    monkeypatch.chdir(tmp_path)
    key = X25519PrivateKey.generate()
    monkeypatch.setenv(
        "LICMGR_SERVER_PRIVATE_KEY", base64.b64encode(key.private_bytes_raw()).decode()
    )
    return key
