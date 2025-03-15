from enum import StrEnum
from functools import lru_cache
from pathlib import Path
from typing import Any, List, Optional

from config_path import ConfigPath
from pydantic import BaseModel, Field, model_validator
from pydantic.types import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict, YamlConfigSettingsSource
from pydantic_settings.sources import PydanticBaseSettingsSource


class ConfigError(ValueError):
    pass


class CaseInsensitiveStrEnum(StrEnum):
    """A string enum that is case-insensitive when comparing values."""

    @classmethod
    @lru_cache(maxsize=128)
    def _missing_(cls, value):
        if not isinstance(value, str):
            return None

        # Try to find a case-insensitive match
        for member in cls:
            if member.lower() == value.lower():
                return member
        return None


class EncryptionMode(CaseInsensitiveStrEnum):
    """Email encryption modes."""

    NONE = "none"
    STARTTLS = "starttls"
    SSL_TLS = "ssl/tls"


class MessageQueueType(CaseInsensitiveStrEnum):
    """Message queue types supported by the application."""

    THREAD = "thread"
    PROCESS = "process"


class SecurityMode(CaseInsensitiveStrEnum):
    """Security modes supported by the application."""

    NONE = "none"
    ALLOWLIST = "allowlist"
    DENYLIST = "denylist"


DEFAULT_SMTP_ENCRYPTION = {
    25: EncryptionMode.NONE,
    587: EncryptionMode.STARTTLS,
    465: EncryptionMode.SSL_TLS,
}


class SMTPConfig(BaseModel):
    username: str = Field(..., alias="Username")
    username: str = Field(..., alias="Username")
    password: SecretStr = Field(..., alias="Password")
    server: str = Field(..., alias="Server")
    port: int = Field(..., alias="Port")
    encryption: Optional[EncryptionMode] = Field(None, alias="Encryption")

    @model_validator(mode="after")
    def validate_encryption(self) -> "SMTPConfig":
        if self.encryption is None:
            try:
                self.encryption = DEFAULT_SMTP_ENCRYPTION[self.port]
            except KeyError as e:
                raise ConfigError(
                    f"Cannot infer encryption mode for non-standard SMTP port {self.port}. "
                    f"Please specify 'Encryption' explicitly."
                ) from e

        return self


class FetchMode(CaseInsensitiveStrEnum):
    MARK_READ = "MarkRead"
    DELETE = "Delete"


DEFAULT_IMAP_ENCRYPTION = {
    143: EncryptionMode.STARTTLS,
    993: EncryptionMode.SSL_TLS,
}


class IMAPConfig(BaseModel):
    username: str = Field(..., alias="Username")
    password: SecretStr = Field(..., alias="Password")
    server: str = Field(..., alias="Server")
    port: int = Field(..., alias="Port")
    encryption: Optional[EncryptionMode] = Field(None, alias="Encryption")

    @model_validator(mode="after")
    def validate_encryption(self) -> "IMAPConfig":
        if self.encryption is None:
            try:
                self.encryption = DEFAULT_IMAP_ENCRYPTION[self.port]
            except KeyError as e:
                raise ConfigError(
                    f"Cannot infer encryption mode for non-standard IMAP port {self.port}. "
                    f"Please specify 'Encryption' explicitly."
                ) from e

        return self


class QueueConfig(BaseModel):
    queue_type: MessageQueueType | None = Field(None, alias="Type")
    parameters: dict[str, Any] = Field(default_factory=dict, alias="Parameters")


class ConcurrencyType(CaseInsensitiveStrEnum):
    THREAD = "Thread"
    PROCESS = "Process"


class WorkerConfig(BaseModel):
    concurrency_type: ConcurrencyType = Field(ConcurrencyType.THREAD, alias="Type")
    count: int = Field(4, alias="Count")


class MailFetchConfig(BaseModel):
    imap: IMAPConfig = Field(..., alias="IMAP")
    workers: WorkerConfig = Field(
        default_factory=lambda: WorkerConfig.model_validate({}),
        alias="Workers",
    )
    queue: QueueConfig = Field(
        default_factory=lambda: QueueConfig.model_validate({}),
        alias="Queue",
    )
    fetch_mode: FetchMode = Field(FetchMode.MARK_READ, alias="Mode")
    fetch_interval: int = Field(60, alias="Interval")


class MailSendConfig(BaseModel):
    send_from: str = Field(..., alias="From")
    smtp: SMTPConfig = Field(..., alias="SMTP")
    workers: WorkerConfig = Field(
        default_factory=lambda: WorkerConfig.model_validate({}),
        alias="Workers",
    )
    queue: QueueConfig = Field(
        default_factory=lambda: QueueConfig.model_validate({}),
        alias="Queue",
    )


class RateLimitConfig(BaseModel):
    limit: Optional[int] = Field(None, alias="Limit")
    window: str = Field("1 hour", alias="Window")


class SecurityConfig(BaseModel):
    mode: SecurityMode = Field(SecurityMode.ALLOWLIST, alias="Mode")
    addresses: List[str] = Field(default_factory=list, alias="Addresses")
    rate_limit: Optional[RateLimitConfig] = Field(None, alias="RateLimit")
    rate_limit_per_sender: Optional[RateLimitConfig] = Field(None, alias="RateLimitPerSender")


class MailBotConfig(BaseModel):
    name: str = Field(..., alias="Name")
    receive: MailFetchConfig = Field(..., alias="Receive")
    send: MailSendConfig = Field(..., alias="Send")
    security: SecurityConfig = Field(
        default_factory=lambda: SecurityConfig.model_validate({}),
        alias="Security",
    )


def config_locations() -> List[Path]:
    unix_common = Path.home() / ".config" / "jbmailbot" / "config.yaml"
    os_convention = ConfigPath("jbmailbot", "pigeonland.net", ".yaml").saveFilePath(mkdir=False)
    return [Path("./config.yaml"), unix_common, Path(os_convention)]


class AppConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        secrets_dir=["/run/secrets", "/var/run/jbmailbot/secrets"],
        env_nested_delimiter="__",
        env_prefix="JBMAILBOT_",
        case_sensitive=False,
        yaml_file=config_locations(),
    )
    mailbots: List[MailBotConfig] = Field(..., alias="MailBots")

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        if cls.model_config.get("yaml_file"):
            yaml_settings = YamlConfigSettingsSource(settings_cls)
            return init_settings, env_settings, dotenv_settings, yaml_settings, file_secret_settings
        else:
            return init_settings, env_settings, dotenv_settings, file_secret_settings
