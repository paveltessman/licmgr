from licmgr.exceptions import LicmgrException


class LicenseServiceException(LicmgrException):
    pass


class LicenseCreationError(LicenseServiceException):
    """A unique license key could not be allocated."""


class InvalidActivationRequestError(LicenseServiceException):
    """The license key or device ID has an invalid format."""


class InvalidLicenseError(LicenseServiceException):
    """The license key has not been issued."""


class DeviceLimitReachedError(LicenseServiceException):
    """The license has no available slots for a new device."""
