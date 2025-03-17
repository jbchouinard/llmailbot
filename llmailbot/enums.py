from enum import StrEnum
from functools import lru_cache


class CaseInsensitiveStrEnum(StrEnum):
    """
    A string enum that is case-insensitive when comparing values.

    Enum values must be lowercase.
    """

    @classmethod
    @lru_cache(maxsize=128)
    def _missing_(cls, value):
        if not isinstance(value, str):
            return None

        # Try to find a case-insensitive match
        for member in cls:
            if member.value == value.lower():
                return member
        return None


class EncryptionMode(CaseInsensitiveStrEnum):
    """Encryption modes for SMTP or IMAP connections."""

    NONE = "none"
    STARTTLS = "starttls"
    SSL_TLS = "ssl/tls"


class QueueType(CaseInsensitiveStrEnum):
    """Identifiers for queue implementations."""

    THREAD = "thread"
    PROCESS = "process"


class OnFetch(CaseInsensitiveStrEnum):
    MARK_READ = "markread"
    DELETE = "delete"


class WorkerType(CaseInsensitiveStrEnum):
    """Worker type for executor pools."""

    THREAD = "thread"
    PROCESS = "process"


class FilterMode(CaseInsensitiveStrEnum):
    """Specify if list is an allowlist or denylist."""

    ALLOWLIST = "allowlist"
    DENYLIST = "denylist"
