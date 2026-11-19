from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.engine import URL
from sqlalchemy.exc import OperationalError

from . import Db
from . import DbError
from . import LicenseRepository
from .licenses import License


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
def repo(database: Db) -> LicenseRepository:
    return LicenseRepository(database)


def test_license_survives_reopening(database: Db, database_url: URL) -> None:
    key = "AAAA-BBBB-CCCC-DDDD"

    added = LicenseRepository(database).add(key, max_devices=3)
    assert added

    with database.transaction() as session:
        license = session.scalars(select(License).where(License.key == key)).one()
        license_id = license.id

    database.close()

    reopened = Db(database_url)

    try:
        reopened.initialize()

        with reopened.transaction() as session:

            license = session.get(License, license_id)

            assert license is not None
            assert license.key == key
            assert license.max_devices == 3

    finally:
        reopened.close()


def test_duplicate_key_preserves_existing_license(database: Db) -> None:
    key = "AAAA-BBBB-CCCC-DDDD"

    repository = LicenseRepository(database)

    added = repository.add(key, max_devices=3)
    assert added

    added_again = repository.add(key, max_devices=5)
    assert not added_again

    with database.transaction() as session:
        license = session.scalars(select(License).where(License.key == key)).one()
        assert license.max_devices == 3


def test_transaction_rolls_back_inserted_license(database: Db) -> None:
    key = "AAAA-BBBB-CCCC-DDDD"

    with pytest.raises(RuntimeError, match="abort"), database.transaction() as session:
        session.add(License(key=key, max_devices=3))
        session.flush()
        raise RuntimeError("abort")

    with database.transaction() as session:
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
