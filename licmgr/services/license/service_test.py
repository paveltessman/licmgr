import re
from unittest.mock import call
from unittest.mock import create_autospec
from unittest.mock import Mock
from unittest.mock import patch

import pytest

from .exceptions import DeviceLimitReachedError
from .exceptions import InvalidActivationRequestError
from .exceptions import InvalidLicenseError
from .exceptions import LicenseCreationError
from .exceptions import LicenseServiceException
from .service import LicenseService
from licmgr.storage import ActivationResult
from licmgr.storage import DbError
from licmgr.storage import LicenseRepo

LICENSE_KEY = "A0AA-BBBB-CCCC-DDDD"
DEVICE_ID = "a1" * 32


@pytest.fixture
def repo() -> Mock:
    return create_autospec(LicenseRepo, instance=True, spec_set=True)


@pytest.fixture
def service(repo: Mock) -> LicenseService:
    return LicenseService(repo)


async def test_create_license_returns_the_key_written_to_the_repo(
    service: LicenseService,
    repo: Mock,
) -> None:
    repo.add.return_value = True

    key = await service.create_license(max_devices=3)

    assert re.fullmatch(r"[A-Z0-9]{4}(?:-[A-Z0-9]{4}){3}", key)
    repo.add.assert_awaited_once_with(key, max_devices=3)


@pytest.mark.parametrize("max_devices", [0, -1])
async def test_create_license_rejects_invalid_device_limits(
    repo: Mock,
    service: LicenseService,
    max_devices: int,
) -> None:
    with pytest.raises(ValueError, match="max_devices must be a positive integer"):
        await service.create_license(max_devices)

    repo.add.assert_not_called()


async def test_create_license_retries_key_collisions(
    repo: Mock,
    service: LicenseService,
) -> None:
    taken_key = "AAAA-BBBB-CCCC-DDDD"
    available_key = "EEEE-FFFF-GGGG-HHHH"
    repo.add.side_effect = [False, True]

    with patch.object(service, "_generate_key", side_effect=[taken_key, available_key]):
        key = await service.create_license(max_devices=3)

    assert key == available_key

    assert repo.add.await_args_list == [
        call(taken_key, max_devices=3),
        call(available_key, max_devices=3),
    ]


async def test_create_license_stops_after_repeated_collisions(
    repo: Mock,
    service: LicenseService,
) -> None:
    repo.add.return_value = False

    with pytest.raises(LicenseCreationError, match="unique license key"):
        await service.create_license(max_devices=3)

    assert repo.add.await_count == 10


async def test_create_license_propagates_database_errors(
    repo: Mock,
    service: LicenseService,
) -> None:
    error = DbError("Database operation failed")
    repo.add.side_effect = error

    with pytest.raises(DbError) as exc:
        await service.create_license(max_devices=3)

    assert exc.value is error
    repo.add.assert_awaited_once()


@pytest.mark.parametrize(
    ("license_key", "device_id"),
    [
        (LICENSE_KEY.lower(), DEVICE_ID),
        ("AAAA-BBBB-CCCC", DEVICE_ID),
        (LICENSE_KEY.replace("-", ""), DEVICE_ID),
        (LICENSE_KEY + "\n", DEVICE_ID),
        (LICENSE_KEY, DEVICE_ID[:-1]),
        (LICENSE_KEY, DEVICE_ID + "0"),
        (LICENSE_KEY, DEVICE_ID.upper()),
        (LICENSE_KEY, "g" + DEVICE_ID[1:]),
        (LICENSE_KEY, DEVICE_ID + "\n"),
    ],
)
async def test_activate_rejects_invalid_fields_before_storage(
    service: LicenseService,
    repo: Mock,
    license_key: str,
    device_id: str,
) -> None:
    with pytest.raises(InvalidActivationRequestError):
        await service.activate(license_key=license_key, device_id=device_id)

    repo.activate.assert_not_called()


@pytest.mark.parametrize(
    ("result", "status"),
    [
        (ActivationResult.ACTIVATED, "activated"),
        (ActivationResult.ALREADY_ACTIVATED, "already_activated"),
    ],
)
async def test_activate_returns_success_status(
    service: LicenseService,
    repo: Mock,
    result: ActivationResult,
    status: str,
) -> None:
    repo.activate.return_value = result

    returned_status = await service.activate(
        license_key=LICENSE_KEY,
        device_id=DEVICE_ID,
    )

    assert returned_status == status
    repo.activate.assert_awaited_once_with(LICENSE_KEY, DEVICE_ID)


@pytest.mark.parametrize(
    ("result", "error"),
    [
        (ActivationResult.INVALID_LICENSE, InvalidLicenseError),
        (ActivationResult.DEVICE_LIMIT_REACHED, DeviceLimitReachedError),
    ],
)
async def test_activate_maps_storage_rejections_to_service_errors(
    service: LicenseService,
    repo: Mock,
    result: ActivationResult,
    error: type[LicenseServiceException],
) -> None:
    repo.activate.return_value = result

    with pytest.raises(error):
        await service.activate(license_key=LICENSE_KEY, device_id=DEVICE_ID)


async def test_activate_propagates_database_errors(
    service: LicenseService,
    repo: Mock,
) -> None:
    error = DbError("Database operation failed")
    repo.activate.side_effect = error

    with pytest.raises(DbError) as exc:
        await service.activate(license_key=LICENSE_KEY, device_id=DEVICE_ID)

    assert exc.value is error
