from uuid import UUID
from uuid import uuid4

from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column

from .base import Base
from .db import Db


class License(Base):
    __tablename__ = "licenses"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    key: Mapped[str] = mapped_column(unique=True)
    max_devices: Mapped[int]


class LicenseRepo:
    def __init__(self, database: Db) -> None:
        self._database = database

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

        with self._database.transaction(immediate=False) as session:
            return session.scalar(statement) is not None
