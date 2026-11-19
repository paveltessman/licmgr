from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from typing import Self

from sqlalchemy import create_engine
from sqlalchemy.engine import URL
from sqlalchemy.exc import DBAPIError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.orm import sessionmaker

from .base import Base
from .exceptions import DbError
from .exceptions import DbIntegrityError

DEFAULT_DB_PATH = "db.sqlite3"


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
        self._engine = create_engine(url)
        self._sessions = sessionmaker(self._engine)

    @classmethod
    def from_sqlite_path(cls, path: Path) -> Self:
        return cls(URL.create("sqlite", database=str(path.absolute())))

    def initialize(self) -> None:
        with _translate_database_errors():
            Base.metadata.create_all(self._engine)

    def close(self) -> None:
        with _translate_database_errors():
            self._engine.dispose()

    @contextmanager
    def transaction(self) -> Generator[Session, None, None]:
        with _translate_database_errors(), self._sessions.begin() as session:
            yield session
