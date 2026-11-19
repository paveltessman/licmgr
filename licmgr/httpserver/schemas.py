import base64
from typing import Annotated

from pydantic import BaseModel
from pydantic import Field
from pydantic import field_validator
from pydantic import StrictInt


class EncryptedRequest(BaseModel):
    version: Annotated[StrictInt, Field(ge=1, le=1)]
    ciphertext: bytes

    @field_validator("ciphertext", mode="before", json_schema_input_type=str)
    @classmethod
    def decode_ciphertext(cls, value: object) -> bytes:
        message = "Expected nonempty ciphertext in standard padded base64"

        if not isinstance(value, str):
            raise ValueError(message)

        try:
            ciphertext = base64.b64decode(value, validate=True)
        except ValueError:
            raise ValueError(message) from None

        if not ciphertext or base64.b64encode(ciphertext).decode("ascii") != value:
            raise ValueError(message)

        return ciphertext


class ApiError(BaseModel):
    code: str
    message: str


class SuccessResponse[T](BaseModel):
    data: T
    error: None = None


class ErrorResponse(BaseModel):
    data: None = None
    error: ApiError
