from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from datetime import UTC
from pathlib import Path
from threading import Barrier
from uuid import UUID
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.engine import URL
from sqlalchemy.exc import OperationalError

from . import ActivationResult
from . import Db
from . import DbError
from . import DbIntegrityError
from . import LicenseRepo
from .licenses import Activation
from .licenses import License

LICENSE_KEY = "AAAA-BBBB-CCCC-DDDD"
DEVICE_ID = "a" * 64
OTHER_DEVICE_ID = "b" * 64


@pytest.fixture
def database_url(tmp_path: Path) -> URL:
    return URL.create("sqlite", database=str(tmp_path / "licenses.db"))


@pytest.fixture
def database(database_url: URL) -> Iterator[Db]:
    database = Db(database_url)
    try:
        database.initialize()
        yield database
    finally:
        database.close()


@pytest.fixture
def repo(database: Db) -> LicenseRepo:
    repo = LicenseRepo(database)
    assert repo.add(LICENSE_KEY, max_devices=1)
    return repo


def test_license_survives_reopening(database: Db, database_url: URL) -> None:
    key = "AAAA-BBBB-CCCC-DDDD"

    added = LicenseRepo(database).add(key, max_devices=3)
    assert added

    with database.transaction(immediate=False) as session:
        license = session.scalars(select(License).where(License.key == key)).one()
        license_id = license.id

    database.close()

    reopened = Db(database_url)

    try:
        reopened.initialize()

        with reopened.transaction(immediate=False) as session:

            license = session.get(License, license_id)

            assert license is not None
            assert license.key == key
            assert license.max_devices == 3

    finally:
        reopened.close()


def test_duplicate_key_preserves_existing_license(database: Db) -> None:
    key = "AAAA-BBBB-CCCC-DDDD"

    repository = LicenseRepo(database)

    added = repository.add(key, max_devices=3)
    assert added

    added_again = repository.add(key, max_devices=5)
    assert not added_again

    with database.transaction(immediate=False) as session:
        license = session.scalars(select(License).where(License.key == key)).one()
        assert license.max_devices == 3


def test_transaction_rolls_back_inserted_license(database: Db) -> None:
    key = "AAAA-BBBB-CCCC-DDDD"

    with pytest.raises(RuntimeError, match="abort"), database.transaction(
        immediate=False
    ) as session:
        session.add(License(key=key, max_devices=3))
        session.flush()
        raise RuntimeError("abort")

    with database.transaction(immediate=False) as session:
        assert session.scalar(select(License).where(License.key == key)) is None


def test_initialize_translates_database_connection_failure(tmp_path: Path) -> None:
    url = URL.create("sqlite", database=str(tmp_path / "missing" / "licenses.db"))
    database = Db(url)
    try:
        with pytest.raises(DbError) as exc:
            database.initialize()
        assert isinstance(exc.value.__cause__, OperationalError)
    finally:
        database.close()


def test_activation_upgrades_existing_database_and_survives_reopening(
    tmp_path: Path,
) -> None:
    path = tmp_path / "licenses.db"
    original = Db.from_sqlite_path(path)
    try:
        with original.transaction(immediate=False) as session:
            License.metadata.tables["licenses"].create(session.connection())
        assert LicenseRepo(original).add(LICENSE_KEY, max_devices=1)
        original.initialize()
        started_at = datetime.now(UTC).replace(microsecond=0)
        assert LicenseRepo(original).activate(LICENSE_KEY, DEVICE_ID) == (
            ActivationResult.ACTIVATED
        )
        finished_at = datetime.now(UTC)
        with original.transaction(immediate=False) as session:
            activation = session.scalars(select(Activation)).one()
            activation_id = activation.id
            assert isinstance(activation_id, UUID)
            assert activation_id.version == 4
            created_at = activation.created_at
            assert started_at <= created_at.replace(tzinfo=UTC) <= finished_at
    finally:
        original.close()

    reopened = Db.from_sqlite_path(path)
    try:
        reopened.initialize()
        repo = LicenseRepo(reopened)

        result = repo.activate(LICENSE_KEY, DEVICE_ID)
        assert result == ActivationResult.ALREADY_ACTIVATED

        result = repo.activate(LICENSE_KEY, OTHER_DEVICE_ID)
        assert result == (ActivationResult.DEVICE_LIMIT_REACHED)

        with reopened.transaction(immediate=False) as session:
            activation = session.scalars(select(Activation)).one()
            assert activation.id == activation_id
            assert activation.created_at == created_at
    finally:
        reopened.close()


def test_license_lookup_is_case_sensitive(repo: LicenseRepo) -> None:
    assert repo.activate(LICENSE_KEY.lower(), DEVICE_ID) == (
        ActivationResult.INVALID_LICENSE
    )
    assert repo.activate(LICENSE_KEY, DEVICE_ID) == ActivationResult.ACTIVATED


def test_capacity_and_device_registration_are_per_license(
    repo: LicenseRepo,
) -> None:
    other_key = "EEEE-FFFF-GGGG-HHHH"
    assert repo.add(other_key, max_devices=2)

    assert repo.activate(LICENSE_KEY, DEVICE_ID) == ActivationResult.ACTIVATED
    assert repo.activate(other_key, DEVICE_ID) == ActivationResult.ACTIVATED
    assert repo.activate(other_key, OTHER_DEVICE_ID) == ActivationResult.ACTIVATED
    assert repo.activate(other_key, "c" * 64) == ActivationResult.DEVICE_LIMIT_REACHED


def test_activation_requires_an_existing_license(database: Db) -> None:
    with pytest.raises(DbIntegrityError), database.transaction(
        immediate=False
    ) as session:
        session.add(Activation(license_id=uuid4(), device_id=DEVICE_ID))


def test_distinct_activation_ids_cannot_register_the_same_device(
    database: Db, repo: LicenseRepo
) -> None:
    assert repo.activate(LICENSE_KEY, DEVICE_ID) == (ActivationResult.ACTIVATED)

    with pytest.raises(DbIntegrityError), database.transaction(
        immediate=False
    ) as session:
        license_id = session.scalars(select(License.id)).one()
        session.add(Activation(license_id=license_id, device_id=DEVICE_ID))


@pytest.mark.parametrize(
    ("second_device_id", "second_result"),
    [
        (DEVICE_ID, ActivationResult.ALREADY_ACTIVATED),
        (OTHER_DEVICE_ID, ActivationResult.DEVICE_LIMIT_REACHED),
    ],
)
def test_concurrent_activations_share_one_slot(
    repo: LicenseRepo, second_device_id: str, second_result: ActivationResult
) -> None:
    barrier = Barrier(2)

    def activate(device_id: str) -> ActivationResult:
        barrier.wait(timeout=5)
        return repo.activate(LICENSE_KEY, device_id)

    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(activate, DEVICE_ID)
        second = executor.submit(activate, second_device_id)
        assert {first.result(), second.result()} == {
            ActivationResult.ACTIVATED,
            second_result,
        }
