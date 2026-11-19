from uuid import UUID
from uuid import uuid4

from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column
from sqlalchemy.orm import Session

from .base import Base


class License(Base):
    __tablename__ = "licenses"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    key: Mapped[str] = mapped_column(unique=True)
    max_devices: Mapped[int]


class LicenseRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, key: str, max_devices: int) -> None:
        self._session.add(License(key=key, max_devices=max_devices))
