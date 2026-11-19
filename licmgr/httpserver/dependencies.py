from fastapi import Request

from licmgr.services.crypto import CryptoService
from licmgr.services.license.service import LicenseService


def get_crypto_service(request: Request) -> CryptoService:
    service: CryptoService = request.app.state.crypto_service
    return service


def get_license_service(request: Request) -> LicenseService:
    service: LicenseService = request.app.state.license_service
    return service
