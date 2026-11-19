from collections.abc import Generator
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy import text
from sqlalchemy.engine import URL
from sqlalchemy.exc import DBAPIError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.orm import sessionmaker

from .base import Base
from .exceptions import DbError
from .exceptions import DbIntegrityError


@contextmanager
def _translate_database_errors() -> Generator[None, None, None]:
    try:
        yield
    except IntegrityError as error:
        raise DbIntegrityError("Database integrity constraint violated") from error
    except DBAPIError as error:
        raise DbError("Database operation failed") from error


class Db:
    def __init__(self, url: str | URL) -> None:
        self._engine = create_engine(url, isolation_level="READ COMMITTED")
        self._sessions = sessionmaker(self._engine)

    def initialize(self) -> None:
        with _translate_database_errors(), self._engine.begin() as connection:
            # Serialize the schema check and creation across CLI and server processes.
            connection.execute(text("SELECT pg_advisory_xact_lock(1818846061)"))
            Base.metadata.create_all(connection)

    def close(self) -> None:
        with _translate_database_errors():
            self._engine.dispose()

    @contextmanager
    def transaction(self) -> Generator[Session, None, None]:
        with _translate_database_errors(), self._sessions.begin() as session:
            yield session


@contextmanager
def open_database(url: str | URL) -> Generator[Db, None, None]:
    database = Db(url)
    try:
        database.initialize()
        yield database
    finally:
        database.close()
