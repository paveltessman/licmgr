import asyncio
from collections.abc import AsyncIterator
from datetime import datetime
from datetime import UTC
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
from . import open_database
from .licenses import Activation
from .licenses import License

LICENSE_KEY = "AAAA-BBBB-CCCC-DDDD"
DEVICE_ID = "a" * 64
OTHER_DEVICE_ID = "b" * 64


@pytest.fixture
async def database(database_url: URL) -> AsyncIterator[Db]:
    async with open_database(database_url) as database:
        yield database


@pytest.fixture
async def repo(database: Db) -> LicenseRepo:
    repo = LicenseRepo(database)
    assert await repo.add(LICENSE_KEY, max_devices=1)
    return repo


async def test_license_survives_reopening(database: Db, database_url: URL) -> None:
    key = "AAAA-BBBB-CCCC-DDDD"

    added = await LicenseRepo(database).add(key, max_devices=3)
    assert added

    async with database.transaction() as session:
        license = (
            await session.scalars(select(License).where(License.key == key))
        ).one()
        license_id = license.id

    await database.close()

    reopened = Db(database_url)

    try:
        await reopened.initialize()

        async with reopened.transaction() as session:

            license = await session.get(License, license_id)

            assert license is not None
            assert license.key == key
            assert license.max_devices == 3

    finally:
        await reopened.close()


async def test_duplicate_key_preserves_existing_license(database: Db) -> None:
    key = "AAAA-BBBB-CCCC-DDDD"

    repository = LicenseRepo(database)

    added = await repository.add(key, max_devices=3)
    assert added

    added_again = await repository.add(key, max_devices=5)
    assert not added_again

    async with database.transaction() as session:
        license = (
            await session.scalars(select(License).where(License.key == key))
        ).one()
        assert license.max_devices == 3


async def test_transaction_rolls_back_inserted_license(database: Db) -> None:
    key = "AAAA-BBBB-CCCC-DDDD"

    with pytest.raises(RuntimeError, match="abort"):
        async with database.transaction() as session:
            session.add(License(key=key, max_devices=3))
            await session.flush()
            raise RuntimeError("abort")

    async with database.transaction() as session:
        assert await session.scalar(select(License).where(License.key == key)) is None


async def test_initialize_translates_database_connection_failure(
    database_url: URL,
) -> None:
    url = database_url.set(database=f"missing_{uuid4().hex}")
    database = Db(url)
    try:
        with pytest.raises(DbError) as exc:
            await database.initialize()
        assert isinstance(exc.value.__cause__, OperationalError)
    finally:
        await database.close()


async def test_activation_survives_reopening(
    database_url: URL,
) -> None:
    original = Db(database_url)
    try:
        await original.initialize()
        assert await LicenseRepo(original).add(LICENSE_KEY, max_devices=1)
        started_at = datetime.now(UTC)
        assert await LicenseRepo(original).activate(LICENSE_KEY, DEVICE_ID) == (
            ActivationResult.ACTIVATED
        )
        finished_at = datetime.now(UTC)
        async with original.transaction() as session:
            activation = (await session.scalars(select(Activation))).one()
            activation_id = activation.id
            assert isinstance(activation_id, UUID)
            assert activation_id.version == 4
            created_at = activation.created_at
            assert started_at <= created_at <= finished_at
    finally:
        await original.close()

    reopened = Db(database_url)
    try:
        await reopened.initialize()
        repo = LicenseRepo(reopened)

        result = await repo.activate(LICENSE_KEY, DEVICE_ID)
        assert result == ActivationResult.ALREADY_ACTIVATED

        result = await repo.activate(LICENSE_KEY, OTHER_DEVICE_ID)
        assert result == (ActivationResult.DEVICE_LIMIT_REACHED)

        async with reopened.transaction() as session:
            activation = (await session.scalars(select(Activation))).one()
            assert activation.id == activation_id
            assert activation.created_at == created_at
    finally:
        await reopened.close()


async def test_license_lookup_is_case_sensitive(repo: LicenseRepo) -> None:
    assert await repo.activate(LICENSE_KEY.lower(), DEVICE_ID) == (
        ActivationResult.INVALID_LICENSE
    )
    assert await repo.activate(LICENSE_KEY, DEVICE_ID) == ActivationResult.ACTIVATED


async def test_capacity_and_device_registration_are_per_license(
    repo: LicenseRepo,
) -> None:
    other_key = "EEEE-FFFF-GGGG-HHHH"
    assert await repo.add(other_key, max_devices=2)

    assert await repo.activate(LICENSE_KEY, DEVICE_ID) == ActivationResult.ACTIVATED
    assert await repo.activate(other_key, DEVICE_ID) == ActivationResult.ACTIVATED
    assert await repo.activate(other_key, OTHER_DEVICE_ID) == ActivationResult.ACTIVATED
    assert (
        await repo.activate(other_key, "c" * 64)
        == ActivationResult.DEVICE_LIMIT_REACHED
    )


async def test_activation_requires_an_existing_license(database: Db) -> None:
    with pytest.raises(DbIntegrityError):
        async with database.transaction() as session:
            session.add(Activation(license_id=uuid4(), device_id=DEVICE_ID))


async def test_distinct_activation_ids_cannot_register_the_same_device(
    database: Db, repo: LicenseRepo
) -> None:
    assert await repo.activate(LICENSE_KEY, DEVICE_ID) == (ActivationResult.ACTIVATED)

    with pytest.raises(DbIntegrityError):
        async with database.transaction() as session:
            license_id = (await session.scalars(select(License.id))).one()
            session.add(Activation(license_id=license_id, device_id=DEVICE_ID))


@pytest.mark.parametrize(
    ("second_device_id", "second_result"),
    [
        (DEVICE_ID, ActivationResult.ALREADY_ACTIVATED),
        (OTHER_DEVICE_ID, ActivationResult.DEVICE_LIMIT_REACHED),
    ],
)
async def test_concurrent_activations_share_one_slot(
    repo: LicenseRepo, second_device_id: str, second_result: ActivationResult
) -> None:
    async with asyncio.timeout(5):
        results = await asyncio.gather(
            repo.activate(LICENSE_KEY, DEVICE_ID),
            repo.activate(LICENSE_KEY, second_device_id),
        )

    assert set(results) == {ActivationResult.ACTIVATED, second_result}
