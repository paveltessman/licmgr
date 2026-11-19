from uuid import UUID
from uuid import uuid4

from sqlalchemy.dialects.sqlite import insert
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

    def add(self, key: str, max_devices: int) -> bool:
        """
        Insert a license and return `True`.
        If the key is already taken, do nothing and return `False`.
        """

        statement = (
            insert(License)
            .values(key=key, max_devices=max_devices)
            .on_conflict_do_nothing(index_elements=[License.key])
            .returning(License.id)
        )

        return self._session.scalar(statement) is not None
