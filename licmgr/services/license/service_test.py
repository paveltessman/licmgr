import re
from unittest.mock import call
from unittest.mock import create_autospec
from unittest.mock import Mock
from unittest.mock import patch

import pytest

from .service import LicenseCreationError
from .service import LicenseService
from licmgr.storage import DbError
from licmgr.storage import LicenseRepo


@pytest.fixture
def repo() -> Mock:
    return create_autospec(LicenseRepo, instance=True, spec_set=True)


@pytest.fixture
def service(repo: Mock) -> LicenseService:
    return LicenseService(repo)


def test_create_license_returns_the_key_written_to_the_repo(
    service: LicenseService,
    repo: Mock,
) -> None:
    repo.add.return_value = True

    key = service.create_license(max_devices=3)

    assert re.fullmatch(r"[A-Z0-9]{4}(?:-[A-Z0-9]{4}){3}", key)
    repo.add.assert_called_once_with(key, max_devices=3)


@pytest.mark.parametrize("max_devices", [0, -1])
def test_create_license_rejects_invalid_device_limits(
    repo: Mock,
    service: LicenseService,
    max_devices: int,
) -> None:
    with pytest.raises(ValueError, match="max_devices must be a positive integer"):
        service.create_license(max_devices)

    repo.add.assert_not_called()


def test_create_license_retries_key_collisions(
    repo: Mock,
    service: LicenseService,
) -> None:
    taken_key = "AAAA-BBBB-CCCC-DDDD"
    available_key = "EEEE-FFFF-GGGG-HHHH"
    repo.add.side_effect = [False, True]

    with patch.object(service, "_generate_key", side_effect=[taken_key, available_key]):
        key = service.create_license(max_devices=3)

    assert key == available_key

    assert repo.add.call_args_list == [
        call(taken_key, max_devices=3),
        call(available_key, max_devices=3),
    ]


def test_create_license_stops_after_repeated_collisions(
    repo: Mock,
    service: LicenseService,
) -> None:
    repo.add.return_value = False

    with pytest.raises(LicenseCreationError, match="unique license key"):
        service.create_license(max_devices=3)

    assert repo.add.call_count == 10


def test_create_license_propagates_database_errors(
    repo: Mock,
    service: LicenseService,
) -> None:
    error = DbError("Database operation failed")
    repo.add.side_effect = error

    with pytest.raises(DbError) as exc:
        service.create_license(max_devices=3)

    assert exc.value is error
    repo.add.assert_called_once()
