import base64
import binascii

from pydantic import field_validator
from pydantic import SecretBytes
from pydantic_settings import BaseSettings
from pydantic_settings import SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", hide_input_in_errors=True)

    LICMGR_SERVER_PRIVATE_KEY: SecretBytes

    def __init__(self) -> None:
        super().__init__()

    @field_validator("LICMGR_SERVER_PRIVATE_KEY", mode="before")
    @classmethod
    def decode_private_key(cls, value: object) -> bytes:
        message = "Expected a 32-byte X25519 private key in standard padded base64"

        if not isinstance(value, str):
            raise ValueError(message)

        try:
            key = base64.b64decode(value, validate=True)
        except (binascii.Error, ValueError):
            raise ValueError(message) from None

        if len(key) != 32 or base64.b64encode(key).decode("ascii") != value:
            raise ValueError(message)

        return key
