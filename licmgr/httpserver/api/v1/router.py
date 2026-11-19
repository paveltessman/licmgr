from fastapi import APIRouter

from .licenses import router as licenses_router

router = APIRouter(prefix="/v1")
router.include_router(licenses_router, prefix="/licenses")
