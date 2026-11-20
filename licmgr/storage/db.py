from collections.abc import AsyncGenerator
from collections.abc import Generator
from contextlib import asynccontextmanager
from contextlib import contextmanager

from sqlalchemy import text
from sqlalchemy.engine import URL
from sqlalchemy.exc import DBAPIError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.ext.asyncio import create_async_engine

from .base import Base
from .exceptions import DbError
from .exceptions import DbIntegrityError


@contextmanager
def _translate_database_errors() -> Generator[None]:
    try:
        yield
    except IntegrityError as error:
        raise DbIntegrityError("Database integrity constraint violated") from error
    except DBAPIError as error:
        raise DbError("Database operation failed") from error


class Db:
    def __init__(self, url: str | URL) -> None:
        self._engine = create_async_engine(url, isolation_level="READ COMMITTED")
        self._sessions = async_sessionmaker(self._engine)

    async def initialize(self) -> None:
        with _translate_database_errors():
            async with self._engine.begin() as connection:
                # Serialize schema initialization across CLI and server processes.
                await connection.execute(
                    text("SELECT pg_advisory_xact_lock(1818846061)")
                )
                await connection.run_sync(Base.metadata.create_all)

    async def close(self) -> None:
        with _translate_database_errors():
            await self._engine.dispose()

    @asynccontextmanager
    async def transaction(self) -> AsyncGenerator[AsyncSession]:
        with _translate_database_errors():
            async with self._sessions.begin() as session:
                yield session


@asynccontextmanager
async def open_database(url: str | URL) -> AsyncGenerator[Db]:
    database = Db(url)
    try:
        await database.initialize()
        yield database
    finally:
        await database.close()
