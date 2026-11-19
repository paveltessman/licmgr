import re
from secrets import choice
from string import ascii_uppercase
from string import digits
from typing import Literal

from .exceptions import DeviceLimitReachedError
from .exceptions import InvalidActivationRequestError
from .exceptions import InvalidLicenseError
from .exceptions import LicenseCreationError
from licmgr.storage import ActivationResult
from licmgr.storage import LicenseRepo

_KEY_ALPHABET = ascii_uppercase + digits
_MAX_KEY_ATTEMPTS = 10


class LicenseService:
    def __init__(self, repo: LicenseRepo) -> None:
        self._repo = repo

    def create_license(self, max_devices: int) -> str:
        """Persist a new license and return its key."""

        if max_devices < 1:
            raise ValueError("max_devices must be a positive integer")

        for _ in range(_MAX_KEY_ATTEMPTS):
            key = self._generate_key()
            added = self._repo.add(key, max_devices=max_devices)

            if added:
                return key

        raise LicenseCreationError("Could not allocate a unique license key")

    def activate(
        self,
        *,
        license_key: str,
        device_id: str,
    ) -> Literal["activated", "already_activated"]:

        self._validate_activation_params(key=license_key, device_id=device_id)

        result = self._repo.activate(license_key, device_id)

        match result:
            case ActivationResult.ACTIVATED:
                return "activated"
            case ActivationResult.ALREADY_ACTIVATED:
                return "already_activated"
            case ActivationResult.INVALID_LICENSE:
                raise InvalidLicenseError("License key has not been issued")
            case ActivationResult.DEVICE_LIMIT_REACHED:
                raise DeviceLimitReachedError("License device limit reached")

    def _generate_key(self) -> str:
        groups = ("".join(choice(_KEY_ALPHABET) for _ in range(4)) for _ in range(4))
        return "-".join(groups)

    def _validate_activation_params(self, *, key: str, device_id: str) -> None:

        if re.fullmatch(r"[A-Z0-9]{4}(?:-[A-Z0-9]{4}){3}", key) is None:
            raise InvalidActivationRequestError("Invalid license key format")

        if re.fullmatch(r"[0-9a-f]{64}", device_id) is None:
            raise InvalidActivationRequestError("Invalid device ID format")
