from typing import Annotated
from typing import Literal

from fastapi import APIRouter
from fastapi import Depends
from pydantic import BaseModel
from pydantic import StrictStr

from licmgr.httpserver.dependencies import get_license_service
from licmgr.httpserver.schemas import ErrorResponse
from licmgr.httpserver.schemas import SuccessResponse
from licmgr.services.license import LicenseService

router = APIRouter(prefix="", tags=["licenses"])


class ActivationRequest(BaseModel):
    license_key: StrictStr
    device_id: StrictStr


class ActivationResult(BaseModel):
    status: Literal["activated", "already_activated"]


@router.post("/activate/", responses={409: {"model": ErrorResponse}})
def activate(
    request: ActivationRequest,
    service: Annotated[LicenseService, Depends(get_license_service)],
) -> SuccessResponse[ActivationResult]:

    status = service.activate(
        license_key=request.license_key,
        device_id=request.device_id,
    )

    return SuccessResponse(data=ActivationResult(status=status))
