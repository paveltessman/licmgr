from licmgr.exceptions import LicmgrException


class DbError(LicmgrException):
    """Database operation failed."""


class DbIntegrityError(DbError):
    """Database integrity constraint was violated."""
