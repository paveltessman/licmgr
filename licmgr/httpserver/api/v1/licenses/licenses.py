from typing import Annotated
from typing import Literal

from fastapi import APIRouter
from fastapi import Depends
from pydantic import BaseModel
from pydantic import StrictStr

from licmgr.httpserver.dependencies import get_crypto_service
from licmgr.httpserver.dependencies import get_license_service
from licmgr.httpserver.schemas import EncryptedRequest
from licmgr.httpserver.schemas import ErrorResponse
from licmgr.httpserver.schemas import SuccessResponse
from licmgr.services.crypto import CryptoService
from licmgr.services.license import LicenseService

router = APIRouter(prefix="", tags=["licenses"])
ACTIVATION_INFO = b"license-activation-v1"


class ActivationRequest(BaseModel):
    license_key: StrictStr
    device_id: StrictStr


class ActivationResult(BaseModel):
    status: Literal["activated", "already_activated"]


@router.post("/activate/", responses={409: {"model": ErrorResponse}})
def activate(
    request: EncryptedRequest,
    service: Annotated[LicenseService, Depends(get_license_service)],
    crypto: Annotated[CryptoService, Depends(get_crypto_service)],
) -> SuccessResponse[ActivationResult]:
    activation = crypto.decrypt(
        request.ciphertext,
        ActivationRequest,
        info=ACTIVATION_INFO,
    )
    status = service.activate(
        license_key=activation.license_key,
        device_id=activation.device_id,
    )

    return SuccessResponse(data=ActivationResult(status=status))
