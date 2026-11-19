import pytest
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
from cryptography.hazmat.primitives.hpke import AEAD
from cryptography.hazmat.primitives.hpke import KDF
from cryptography.hazmat.primitives.hpke import KEM
from cryptography.hazmat.primitives.hpke import Suite
from pydantic import BaseModel
from pydantic import StrictInt

from .exceptions import InvalidEncryptedPayloadError
from .service import CryptoService

INFO = b"license-activation-v1"
SUITE = Suite(KEM.X25519, KDF.HKDF_SHA256, AEAD.AES_128_GCM)


class Payload(BaseModel):
    count: StrictInt


@pytest.fixture
def private_key() -> X25519PrivateKey:
    return X25519PrivateKey.generate()


@pytest.fixture
def ciphertext(private_key: X25519PrivateKey) -> bytes:
    return SUITE.encrypt(b'{"count":3}', private_key.public_key(), info=INFO)


def test_decrypts_to_requested_model(
    private_key: X25519PrivateKey, ciphertext: bytes
) -> None:
    assert CryptoService(private_key).decrypt(ciphertext, Payload, info=INFO) == (
        Payload(count=3)
    )


def test_rejects_truncated_and_tampered_ciphertext(
    private_key: X25519PrivateKey,
    ciphertext: bytes,
) -> None:
    service = CryptoService(private_key)
    tampered = ciphertext[:-1] + bytes([ciphertext[-1] ^ 1])
    for invalid in (ciphertext[:16], tampered):
        with pytest.raises(
            InvalidEncryptedPayloadError, match="Invalid encrypted payload"
        ):
            service.decrypt(invalid, Payload, info=INFO)


def test_rejects_wrong_key(ciphertext: bytes) -> None:
    with pytest.raises(InvalidEncryptedPayloadError):
        CryptoService(X25519PrivateKey.generate()).decrypt(
            ciphertext, Payload, info=INFO
        )


def test_rejects_wrong_info(private_key: X25519PrivateKey, ciphertext: bytes) -> None:
    with pytest.raises(InvalidEncryptedPayloadError):
        CryptoService(private_key).decrypt(ciphertext, Payload, info=b"other")


@pytest.mark.parametrize("plaintext", [b"{", b'{"count":"private"}', b"{}"])
def test_rejects_invalid_inner_payload(
    private_key: X25519PrivateKey, plaintext: bytes
) -> None:
    ciphertext = SUITE.encrypt(plaintext, private_key.public_key(), info=INFO)

    with pytest.raises(InvalidEncryptedPayloadError) as exc_info:
        CryptoService(private_key).decrypt(ciphertext, Payload, info=INFO)

    assert str(exc_info.value) == "Invalid encrypted payload"
    assert exc_info.value.__context__ is None
