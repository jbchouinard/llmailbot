from __future__ import annotations

import datetime
import re
from pathlib import Path
from typing import Annotated, Any, ClassVar, List, Literal, TypeVar

import yaml
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
from llmailbot.enums import (
    EncryptionMode,
    FilterMode,
    OnFetch,
    VerifyMode,
    WorkerType,
)


class ConfigError(ValueError):
    pass


T = TypeVar("T")
type Opt[T] = T | None


Port = Annotated[int, Ge(1), Le(65535)]
Temperature = Annotated[float, Ge(0.0), Le(1.0)]


def snake_to_camel_case(snake_str: str) -> str:
    return "".join(word.title() for word in snake_str.split("_"))


def camel_to_snake_case(camel_str: str) -> str:
    # Insert underscore before uppercase letters and convert to lowercase
    snake_str = re.sub(r"(?<!^)(?=[A-Z])", "_", camel_str).lower()
    return snake_str


class ConfigModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=snake_to_camel_case,
        populate_by_name=True,
    )


class SMTPConfig(ConfigModel):
    default_encryption_by_port: Annotated[dict[Port, EncryptionMode], ClassVar] = {
        25: EncryptionMode.NONE,
        587: EncryptionMode.STARTTLS,
        465: EncryptionMode.SSL_TLS,
    }

    username: str = Field(...)
    password: SecretStr = Field(...)
    server: str = Field(...)
    port: Port = Field(465)
    encryption: Opt[EncryptionMode] = Field(None)

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


class IMAPConfig(ConfigModel):
    default_encryption_by_port: Annotated[dict[Port, EncryptionMode], ClassVar] = {
        143: EncryptionMode.STARTTLS,
        993: EncryptionMode.SSL_TLS,
    }

    # Mail server settings
    username: str = Field(...)
    password: SecretStr = Field(...)
    server: str = Field(...)
    port: Port = Field(993)
    encryption: Annotated[Opt[EncryptionMode], Field()] = None

    # Fetch settings
    on_fetch: Annotated[OnFetch, Field()] = OnFetch.MARK_READ
    fetch_interval: Annotated[PositiveInt, Field()] = 300
    fetch_max: Annotated[PositiveInt, Field()] = 10
    fetch_max_age_days: Annotated[NonNegativeInt, Field()] = 1

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


class MemoryQueueSettings(ConfigModel):
    queue_type: Annotated[Literal["Memory"], Field(alias="Type")] = "Memory"
    max_size: Annotated[NonNegativeInt, Field()] = 0
    timeout: Annotated[PositiveInt, Field()] = 10


class RedisConfig(ConfigModel):
    host: Annotated[str, Field()] = "localhost"
    port: Annotated[Port, Field()] = 6379
    db: Annotated[NonNegativeInt, Field()] = 0
    username: Annotated[Opt[str], Field()] = None
    password: Annotated[Opt[str], Field()] = None


class RedisQueueSettings(RedisConfig):
    queue_type: Annotated[Literal["Redis"], Field(alias="Type")] = "Redis"
    key: str = Field(...)
    timeout: Annotated[NonNegativeInt, Field()] = 10


type QueueSettings = MemoryQueueSettings | RedisQueueSettings


class WorkerPoolConfig(ConfigModel):
    worker_type: Annotated[WorkerType, Field()] = WorkerType.THREAD
    count: Annotated[PositiveInt, Field()] = 4


class RateLimitConfig(ConfigModel):
    limit: PositiveInt = Field(...)
    window: Annotated[str, Field()] = "1 hour"

    _window_timedelta: datetime.timedelta

    @model_validator(mode="after")
    def validate_window(self) -> RateLimitConfig:
        self._window_timedelta = parse_duration(self.window)
        return self


class FilterHeaderConfig(ConfigModel):
    header: str = Field(...)
    values: List[str] = Field(default_factory=list)
    mode: Annotated[FilterMode, Field()] = FilterMode.ALLOWLIST
    verify: Annotated[VerifyMode, Field()] = VerifyMode.ALWAYS


class SecurityConfig(ConfigModel):
    rate_limit: RateLimitConfig = Field(
        default_factory=lambda: RateLimitConfig.model_validate({"Limit": 100, "Window": "1 day"})
    )
    rate_limit_per_sender: Annotated[Opt[RateLimitConfig], Field()] = None
    rate_limit_per_domain: Annotated[Opt[RateLimitConfig], Field()] = None

    # Secure default: dont allow any addresses
    allow_from: List[EmailStr] = Field(default_factory=list)
    allow_from_all_i_want_to_spend_it_all: Annotated[
        bool, Field(alias="AllowAllAddressesIReallyDontMindSpendingAllMyCredits")
    ] = False
    block_from: Annotated[Opt[List[EmailStr]], Field()] = None

    filter_headers: Annotated[Opt[List[FilterHeaderConfig]], Field()] = None

    verify_dkim: Annotated[VerifyMode, Field(alias="VerifyDKIM")] = VerifyMode.NEVER
    verify_mail_from: Annotated[VerifyMode, Field()] = VerifyMode.NEVER
    verify_x_mail_from: Annotated[VerifyMode, Field()] = VerifyMode.NEVER


class ChatModelConfig(ConfigModel):
    model_config = ConfigDict(extra="allow")
    model: Opt[str] = None
    model_provider: Opt[str] = None
    max_tokens: PositiveInt = 1024
    temperature: Temperature = 0.2

    def chat_model_config(self) -> dict[str, Any]:
        config = self.model_dump()
        return {camel_to_snake_case(k): v for k, v in config.items()}


class ModelSpec(ConfigModel):
    name: str = Field(...)

    address: Annotated[Opt[EmailStr], Field()] = None
    address_regex: Annotated[Opt[str], Field()] = None

    max_input_length: Annotated[PositiveInt, Field()] = 5000
    system_prompt: str = Field(...)

    params: ChatModelConfig = Field(
        default_factory=lambda: ChatModelConfig(),
        alias="ChatModelConfig",
    )

    _address_regex: Opt[re.Pattern[str]]

    @model_validator(mode="after")
    def validate_exactly_one_email_addr(self) -> ModelSpec:
        if self.address_regex is not None and self.address is None:
            return self
        if self.address is not None and self.address_regex is None:
            return self
        raise ConfigError("exactly one of Address or AddressRegex must be set")

    @model_validator(mode="after")
    def validate_address_regex(self) -> ModelSpec:
        if self.address_regex is not None:
            try:
                self._address_regex = re.compile(self.address_regex)
            except re.error as e:
                raise ConfigError(f"invalid regex: {e}") from e
        else:
            self._address_regex = None
        return self

    def chat_model_config(self, email_addr: Opt[str] = None) -> dict[str, Any]:
        model_config = self.params.chat_model_config()
        if email_addr and self._address_regex:
            if m := self._address_regex.match(email_addr):
                for k, v in m.groupdict().items():
                    if v is not None:
                        model_config[k.lower()] = v

        return model_config


def yaml_config_locations() -> List[Path]:
    unix_common = Path.home() / ".config" / "llmailbot" / "config.yaml"
    os_convention = ConfigPath("llmailbot", "pigeonland.net", ".yaml").saveFilePath(mkdir=False)
    return [Path("./config.yaml"), unix_common, Path(os_convention)]


def secrets_dirs():
    paths = [Path("/run/secrets"), Path("/var/run/llmailbot/secrets")]
    return [p for p in paths if p.exists()]


DEFAULT_QUEUE_SETTINGS = {
    "receive": {
        WorkerType.THREAD: MemoryQueueSettings(),
        WorkerType.PROCESS: RedisQueueSettings(key="llmailbot-incoming-mail"),
    },
    "send": {
        WorkerType.THREAD: MemoryQueueSettings(),
        WorkerType.PROCESS: RedisQueueSettings(key="llmailbot-outgoing-mail"),
    },
}


class LLMailBotConfig(BaseSettings):
    model_config = SettingsConfigDict(
        alias_generator=snake_to_camel_case,
        case_sensitive=False,
        extra="ignore",
        secrets_dir=secrets_dirs(),
        yaml_file=yaml_config_locations(),
    )
    models: List[ModelSpec] = Field(...)
    chat_model_configurable_fields: Annotated[Opt[set[str]], Field()] = None

    security: SecurityConfig = Field(default_factory=lambda: SecurityConfig())

    imap: IMAPConfig = Field(..., alias="IMAP")
    smtp: SMTPConfig = Field(..., alias="SMTP")

    worker_pool: WorkerPoolConfig = Field(default_factory=lambda: WorkerPoolConfig())

    receive_queue: Annotated[Opt[QueueSettings], Field()] = None
    send_queue: Annotated[Opt[QueueSettings], Field()] = None

    @model_validator(mode="after")
    def normalize_chat_model_configurable_fields(self) -> LLMailBotConfig:
        if self.chat_model_configurable_fields is not None:
            self.chat_model_configurable_fields = set(
                [camel_to_snake_case(f) for f in self.chat_model_configurable_fields]
            )
        return self

    @model_validator(mode="after")
    def validate_unique_bot_addresses(self) -> LLMailBotConfig:
        addresses = [bot.address for bot in self.models]
        if len(addresses) != len(set(addresses)):
            raise ConfigError("Each mailbot must use a unique email address")
        return self

    @model_validator(mode="after")
    def set_queue_type_none_to_default(self):
        if self.receive_queue is None:
            self.receive_queue = DEFAULT_QUEUE_SETTINGS["receive"][self.worker_pool.worker_type]
        if self.send_queue is None:
            self.send_queue = DEFAULT_QUEUE_SETTINGS["send"][self.worker_pool.worker_type]
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
            return init_settings, yaml_settings, file_secret_settings
        else:
            return init_settings, file_secret_settings

    def dump_yaml(self) -> str:
        return yaml.dump(self.model_dump(mode="json", by_alias=True), sort_keys=False)
