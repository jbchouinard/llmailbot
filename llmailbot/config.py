from __future__ import annotations

import datetime
import re
from pathlib import Path
from typing import Annotated, Any, ClassVar, List

from annotated_types import Ge, Le
from config_path import ConfigPath
from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    NonNegativeInt,
    PositiveInt,
    SecretStr,
    model_validator,
)
from pydantic_settings import BaseSettings, SettingsConfigDict, YamlConfigSettingsSource
from pydantic_settings.sources import PydanticBaseSettingsSource

from llmailbot.duration import parse_duration
from llmailbot.enums import EncryptionMode, FilterMode, OnFetch, QueueType, WorkerType


class ConfigError(ValueError):
    pass


Port = Annotated[int, Ge(1), Le(65535)]
Temperature = Annotated[float, Ge(0.0), Le(1.0)]


class SMTPConfig(BaseModel):
    default_encryption_by_port: Annotated[dict[Port, EncryptionMode], ClassVar] = {
        25: EncryptionMode.NONE,
        587: EncryptionMode.STARTTLS,
        465: EncryptionMode.SSL_TLS,
    }

    username: str = Field(..., alias="Username")
    password: SecretStr = Field(..., alias="Password")
    server: str = Field(..., alias="Server")
    port: Port = Field(..., alias="Port")
    encryption: EncryptionMode | None = Field(None, alias="Encryption")

    @model_validator(mode="after")
    def validate_encryption(self) -> SMTPConfig:
        if self.encryption is None:
            try:
                self.encryption = self.default_encryption_by_port[self.port]
            except KeyError as e:
                raise ConfigError(
                    f"Cannot infer encryption mode for non-standard SMTP port {self.port}. "
                    f"Please specify 'Encryption' explicitly."
                ) from e

        return self


class IMAPConfig(BaseModel):
    default_encryption_by_port: Annotated[dict[Port, EncryptionMode], ClassVar] = {
        143: EncryptionMode.STARTTLS,
        993: EncryptionMode.SSL_TLS,
    }

    username: str = Field(..., alias="Username")
    password: SecretStr = Field(..., alias="Password")
    server: str = Field(..., alias="Server")
    port: Port = Field(..., alias="Port")
    encryption: EncryptionMode | None = Field(None, alias="Encryption")

    @model_validator(mode="after")
    def validate_encryption(self) -> IMAPConfig:
        if self.encryption is None:
            try:
                self.encryption = self.default_encryption_by_port[self.port]
            except KeyError as e:
                raise ConfigError(
                    f"Cannot infer encryption mode for non-standard IMAP port {self.port}. "
                    f"Please specify 'Encryption' explicitly."
                ) from e

        return self


class MailFetchConfig(BaseModel):
    imap: IMAPConfig = Field(..., alias="IMAP")
    fetch_mode: OnFetch = Field(OnFetch.MARK_READ, alias="Mode")
    fetch_interval: PositiveInt = Field(60, alias="Interval")
    max_age_days: NonNegativeInt = Field(1, alias="MaxAgeDays")
    batch_size: PositiveInt = Field(10, alias="BatchSize")


class MailSendConfig(BaseModel):
    smtp: SMTPConfig = Field(..., alias="SMTP")


class QueueConfig(BaseModel):
    queue_type: Annotated[QueueType | None, Field(alias="Type")] = None
    parameters: dict[str, Any] = Field(default_factory=dict, alias="Parameters")
    timeout: Annotated[PositiveInt, Field(alias="Timeout")] = 10


class WorkerPoolConfig(BaseModel):
    worker_type: Annotated[WorkerType, Field(alias="Type")] = WorkerType.THREAD
    count: Annotated[PositiveInt, Field(alias="Count")] = 4


class RateLimitConfig(BaseModel):
    limit: PositiveInt = Field(..., alias="Limit")
    window: Annotated[str, Field(alias="Window")] = "1 hour"

    _window_timedelta: datetime.timedelta

    @model_validator(mode="after")
    def validate_window(self) -> RateLimitConfig:
        self._window_timedelta = parse_duration(self.window)
        return self


class FilterConfig(BaseModel):
    mode: Annotated[FilterMode, Field(alias="Mode")] = FilterMode.ALLOWLIST
    addresses: List[EmailStr] = Field(default_factory=list, alias="Addresses")


class SecurityConfig(BaseModel):
    secret_key: Annotated[SecretStr | None, Field(alias="SecretKey")] = None
    workers: Annotated[PositiveInt, Field(alias="Workers")] = 1
    filter_from: FilterConfig = Field(
        default_factory=lambda: FilterConfig(),
        alias="FilterFrom",
    )
    rate_limit_global: Annotated[RateLimitConfig | None, Field(alias="RateLimit")] = None
    rate_limit_per_sender: Annotated[RateLimitConfig | None, Field(alias="RateLimitPerSender")] = (
        None
    )
    rate_limit_per_domain: Annotated[RateLimitConfig | None, Field(alias="RateLimitPerDomain")] = (
        None
    )


class ChatModelConfig(BaseModel):
    model_config = ConfigDict(extra="allow")
    model: str | None = None
    model_provider: str | None = None
    max_tokens: PositiveInt = 1024
    temperature: Temperature = 0.2

    def chat_model_config(self) -> dict[str, Any]:
        config = self.model_extra or {}
        config = {k.lower(): v for k, v in config.items()}
        config.update(
            {
                "model": self.model,
                "model_provider": self.model_provider,
                "max_tokens": self.max_tokens,
                "temperature": self.temperature,
            }
        )
        return config


class MailBotSpec(BaseModel):
    name: str = Field(..., alias="Name")

    address: EmailStr | None = Field(None, alias="Address")
    address_regex: str | None = Field(None, alias="AddressRegex")

    max_input_length: PositiveInt = Field(5000, alias="MaxInputLength")
    system_prompt: str = Field(..., alias="SystemPrompt")

    model_params: ChatModelConfig = Field(
        default_factory=lambda: ChatModelConfig(),
        alias="ChatModelConfig",
    )

    _address_regex: re.Pattern[str] | None

    @model_validator(mode="after")
    def validate_exactly_one_email_addr(self) -> MailBotSpec:
        if self.address_regex is not None and self.address is None:
            return self
        if self.address is not None and self.address_regex is None:
            return self
        raise ConfigError("exactly one of Address or AddressRegex must be set")

    @model_validator(mode="after")
    def validate_address_regex(self) -> MailBotSpec:
        if self.address_regex is not None:
            try:
                self._address_regex = re.compile(self.address_regex)
            except re.error as e:
                raise ConfigError(f"invalid regex: {e}") from e
        else:
            self._address_regex = None
        return self

    def chat_model_config(self, email_addr: str | None = None) -> dict[str, Any]:
        model_config = self.model_params.chat_model_config()
        if email_addr and self._address_regex:
            if m := self._address_regex.match(email_addr):
                for k, v in m.groupdict().items():
                    if v is not None:
                        model_config[k.lower()] = v

        return model_config


def config_locations() -> List[Path]:
    unix_common = Path.home() / ".config" / "llmailbot" / "config.yaml"
    os_convention = ConfigPath("llmailbot", "pigeonland.net", ".yaml").saveFilePath(mkdir=False)
    return [Path("./config.yaml"), unix_common, Path(os_convention)]


DEFAULT_QUEUE_TYPE = {
    WorkerType.THREAD: QueueType.THREAD,
    WorkerType.PROCESS: QueueType.PROCESS,
}


def secrets_dir():
    paths = [Path("/run/secrets"), Path("/var/run/llmailbot/secrets")]
    return [p for p in paths if p.exists()]


class AppConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        secrets_dir=secrets_dir(),
        env_nested_delimiter="__",
        env_prefix="LLMAILBOT_",
        case_sensitive=False,
        yaml_file=config_locations(),
        extra="ignore",
    )
    mailbots: List[MailBotSpec] = Field(..., alias="MailBots")
    mailfetch: MailFetchConfig = Field(..., alias="MailFetch")
    mailsend: MailSendConfig = Field(..., alias="MailSend")
    chat_model_configurable_fields: set[str] | None = Field(
        None, alias="ChatModelConfigurableFields"
    )
    queues: QueueConfig = Field(
        default_factory=lambda: QueueConfig(),
        alias="Queues",
    )
    worker_pool: WorkerPoolConfig = Field(
        default_factory=lambda: WorkerPoolConfig(),
        alias="WorkerPool",
    )
    security: SecurityConfig = Field(
        default_factory=lambda: SecurityConfig(),
        alias="Security",
    )

    @model_validator(mode="after")
    def validate_unique_bot_addresses(self) -> AppConfig:
        addresses = [bot.address for bot in self.mailbots]
        if len(addresses) != len(set(addresses)):
            raise ConfigError("Each mailbot must use a unique email address")
        return self

    @model_validator(mode="after")
    def set_queue_type_none_to_default(self):
        if self.queues.queue_type is None:
            self.queues.queue_type = DEFAULT_QUEUE_TYPE[self.worker_pool.worker_type]
        return self

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
