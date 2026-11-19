import base64
import binascii

from pydantic import field_validator
from pydantic import SecretBytes
from pydantic import SecretStr
from pydantic_settings import BaseSettings
from pydantic_settings import SettingsConfigDict
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError


class DatabaseSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", hide_input_in_errors=True, extra="ignore"
    )

    LICMGR_DATABASE_URL: SecretStr

    def __init__(self) -> None:
        super().__init__()

    @field_validator("LICMGR_DATABASE_URL")
    @classmethod
    def validate_database_url(cls, value: SecretStr) -> SecretStr:
        message = "Expected a PostgreSQL URL using Psycopg 3"
        try:
            url = make_url(value.get_secret_value())
        except (ArgumentError, ValueError):
            raise ValueError(message) from None
        if url.drivername not in {"postgresql", "postgresql+psycopg"}:
            raise ValueError(message)
        url = url.set(drivername="postgresql+psycopg")
        return SecretStr(url.render_as_string(hide_password=False))


class Settings(DatabaseSettings):
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
