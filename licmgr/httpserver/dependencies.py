from fastapi import Request

from licmgr.services.license.service import LicenseService


def get_license_service(request: Request) -> LicenseService:
    service: LicenseService = request.app.state.license_service
    return service
