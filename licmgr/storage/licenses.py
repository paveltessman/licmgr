from datetime import datetime
from enum import StrEnum
from uuid import UUID
from uuid import uuid4

from sqlalchemy import DateTime
from sqlalchemy import ForeignKey
from sqlalchemy import func
from sqlalchemy import select
from sqlalchemy import UniqueConstraint
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column

from .base import Base
from .db import Db


class License(Base):
    __tablename__ = "licenses"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    key: Mapped[str] = mapped_column(unique=True)
    max_devices: Mapped[int]


class Activation(Base):
    __tablename__ = "activations"
    __table_args__ = (UniqueConstraint("license_id", "device_id"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    license_id: Mapped[UUID] = mapped_column(ForeignKey("licenses.id"))
    device_id: Mapped[str]
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.current_timestamp()
    )


class ActivationResult(StrEnum):
    ACTIVATED = "activated"
    ALREADY_ACTIVATED = "already_activated"
    INVALID_LICENSE = "invalid_license"
    DEVICE_LIMIT_REACHED = "device_limit_reached"


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

        with self._database.transaction() as session:
            return session.scalar(statement) is not None

    def activate(self, license_key: str, device_id: str) -> ActivationResult:
        with self._database.transaction() as session:
            license = session.scalar(
                select(License).where(License.key == license_key).with_for_update()
            )
            if license is None:
                return ActivationResult.INVALID_LICENSE

            activation_id = session.scalar(
                select(Activation.id).where(
                    Activation.license_id == license.id,
                    Activation.device_id == device_id,
                )
            )
            if activation_id is not None:
                return ActivationResult.ALREADY_ACTIVATED

            count = session.execute(
                select(func.count())
                .select_from(Activation)
                .where(Activation.license_id == license.id)
            ).scalar_one()

            if count >= license.max_devices:
                return ActivationResult.DEVICE_LIMIT_REACHED

            session.add(Activation(license_id=license.id, device_id=device_id))
            return ActivationResult.ACTIVATED
