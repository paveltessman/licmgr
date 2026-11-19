from licmgr.exceptions import LicmgrException


class InvalidEncryptedPayloadError(LicmgrException):
    """An encrypted payload could not be decrypted or validated."""
