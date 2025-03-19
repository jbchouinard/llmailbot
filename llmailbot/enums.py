import re
from enum import StrEnum
from functools import lru_cache


class CaseInsensitiveStrEnum(StrEnum):
    """
    A string enum that is whitespace-insensitive and case-insensitive when comparing values.
    """

    @staticmethod
    def _normalize(value: str) -> str:
        return re.sub(r"\s+", "", value).lower()

    @classmethod
    @lru_cache(maxsize=128)
    def _missing_(cls, value):
        if not isinstance(value, str):
            return None

        normalized_value = cls._normalize(value)
        for member in cls:
            if cls._normalize(member.value) == normalized_value:
                return member
        return None


class EncryptionMode(CaseInsensitiveStrEnum):
    """Encryption modes for SMTP or IMAP connections."""

    NONE = "none"
    STARTTLS = "starttls"
    SSL_TLS = "ssl/tls"


class OnFetch(CaseInsensitiveStrEnum):
    MARK_READ = "mark read"
    DELETE = "delete"


class WorkerType(CaseInsensitiveStrEnum):
    """Worker type for executor pools."""

    THREAD = "thread"
    PROCESS = "process"


class FilterMode(CaseInsensitiveStrEnum):
    """Specify if list is an allowlist or denylist."""

    ALLOWLIST = "allow list"
    DENYLIST = "deny list"


class VerifyMode(CaseInsensitiveStrEnum):
    NEVER = "never"
    IF_PRESENT = "if present"
    ALWAYS = "always"
