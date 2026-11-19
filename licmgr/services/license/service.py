from secrets import choice
from string import ascii_uppercase
from string import digits

from licmgr.exceptions import LicmgrException
from licmgr.storage import LicenseRepo

_KEY_ALPHABET = ascii_uppercase + digits
_MAX_KEY_ATTEMPTS = 10


class LicenseCreationError(LicmgrException):
    """A unique license key could not be allocated."""


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

    def _generate_key(self) -> str:
        groups = ("".join(choice(_KEY_ALPHABET) for _ in range(4)) for _ in range(4))
        return "-".join(groups)
