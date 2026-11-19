from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
from cryptography.hazmat.primitives.hpke import AEAD
from cryptography.hazmat.primitives.hpke import KDF
from cryptography.hazmat.primitives.hpke import KEM
from cryptography.hazmat.primitives.hpke import Suite
from pydantic import BaseModel
from pydantic import ValidationError

from .exceptions import InvalidEncryptedPayloadError


class CryptoService:
    def __init__(self, private_key: X25519PrivateKey) -> None:
        self._private_key = private_key
        self._suite = Suite(KEM.X25519, KDF.HKDF_SHA256, AEAD.AES_128_GCM)

    def decrypt[T: BaseModel](
        self,
        ciphertext: bytes,
        model: type[T],
        *,
        info: bytes,
    ) -> T:
        """Open an HPKE message and validate its JSON against the supplied model."""

        try:
            plain = self._suite.decrypt(ciphertext, self._private_key, info=info)
            return model.model_validate_json(plain)

        except (InvalidTag, ValidationError):
            pass

        # Pydantic validation errors can carry decrypted input.
        raise InvalidEncryptedPayloadError("Invalid encrypted payload")
