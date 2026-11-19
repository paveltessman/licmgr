import os
from collections.abc import Iterator
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.engine import URL
from sqlalchemy.schema import CreateSchema
from sqlalchemy.schema import DropSchema


@pytest.fixture
def database_url(monkeypatch: pytest.MonkeyPatch) -> Iterator[URL]:
    base_url = os.environ.get("LICMGR_TEST_DATABASE_URL")
    if base_url is None:
        pytest.fail("Set LICMGR_TEST_DATABASE_URL to a PostgreSQL test database")

    url = make_url(base_url).set(drivername="postgresql+psycopg")
    schema = f"licmgr_test_{uuid4().hex}"
    options = url.query.get("options", "")
    assert isinstance(options, str)
    test_url = url.update_query_dict({"options": f"{options} -csearch_path={schema}"})
    engine = create_engine(url)
    try:
        with engine.begin() as connection:
            connection.execute(CreateSchema(schema))
        monkeypatch.setenv(
            "LICMGR_DATABASE_URL", test_url.render_as_string(hide_password=False)
        )
        try:
            yield test_url
        finally:
            with engine.begin() as connection:
                connection.execute(DropSchema(schema, cascade=True))
    finally:
        engine.dispose()
