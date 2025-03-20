# pyright: reportCallIssue=false
import datetime
from typing import Tuple

import pytest
from pydantic import SecretStr, ValidationError
from pydantic_settings import BaseSettings
from pydantic_settings.sources import PydanticBaseSettingsSource

from llmailbot.config import (
    ChatModelConfig,
    FetchConfig,
    FilterHeaderConfig,
    FilterMode,
    IMAPConfig,
    MemoryQueueSettings,
    ModelSpec,
    OnFetch,
    RateLimitConfig,
    RedisQueueSettings,
    ReplyConfig,
    RootSettings,
    SecurityConfig,
    SendConfig,
    SMTPConfig,
    VerifyMode,
    WorkerPoolConfig,
    WorkerType,
    camel_to_snake_case,
    snake_to_camel_case,
)
from llmailbot.enums import EncryptionMode


# Create test-specific base classes that override settings_customise_sources
class IsolatedRootSettings(RootSettings):
    """Base class for testing RootSettings subclasses without loading external config."""

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> Tuple[PydanticBaseSettingsSource, ...]:
        # Only use init_settings for testing to avoid loading from files or env
        return (init_settings,)


def test_snake_to_camel_case():
    assert snake_to_camel_case("snake_case_string") == "SnakeCaseString"
    assert snake_to_camel_case("single") == "Single"
    # The function doesn't preserve case in the middle of words
    assert snake_to_camel_case("already_PascalCase") == "AlreadyPascalcase"
    assert snake_to_camel_case("with_123_numbers") == "With123Numbers"
    assert snake_to_camel_case("trailing_underscore_") == "TrailingUnderscore"
    assert snake_to_camel_case("_leading_underscore") == "LeadingUnderscore"


def test_camel_to_snake_case():
    assert camel_to_snake_case("CamelCaseString") == "camel_case_string"
    assert camel_to_snake_case("Single") == "single"
    assert camel_to_snake_case("already_snake_case") == "already_snake_case"
    assert camel_to_snake_case("With123Numbers") == "with123_numbers"
    assert camel_to_snake_case("ABCDef") == "a_b_c_def"


class TestSMTPConfig:
    def test_valid_config(self):
        # Test with explicit encryption
        config = SMTPConfig(
            username="user@example.com",
            password=SecretStr("password"),
            server="smtp.example.com",
            port=587,
            encryption=EncryptionMode.STARTTLS,
        )
        assert config.username == "user@example.com"
        assert config.password.get_secret_value() == "password"
        assert config.server == "smtp.example.com"
        assert config.port == 587
        assert config.encryption == EncryptionMode.STARTTLS

    def test_default_encryption_inference(self):
        # Test standard ports with default encryption
        standard_ports = {
            25: EncryptionMode.NONE,
            587: EncryptionMode.STARTTLS,
            465: EncryptionMode.SSL_TLS,
        }

        for port, expected_encryption in standard_ports.items():
            config = SMTPConfig(
                username="user@example.com",
                password=SecretStr("password"),
                server="smtp.example.com",
                port=port,
            )
            assert config.encryption == expected_encryption

    def test_non_standard_port_requires_encryption(self):
        # Test non-standard port requires explicit encryption
        with pytest.raises(ValidationError) as exc_info:
            SMTPConfig(
                username="user@example.com",
                password=SecretStr("password"),
                server="smtp.example.com",
                port=1234,  # Non-standard port
            )
        assert "Cannot infer encryption mode" in str(exc_info.value)


class TestIMAPConfig:
    def test_valid_config(self):
        # Test with explicit encryption
        config = IMAPConfig(
            username="user@example.com",
            password=SecretStr("password"),
            server="imap.example.com",
            port=993,
            encryption=EncryptionMode.SSL_TLS,
            on_fetch=OnFetch.MARK_READ,
            fetch_interval=300,
            fetch_max=10,
            fetch_max_age_days=1,
        )
        assert config.username == "user@example.com"
        assert config.password.get_secret_value() == "password"
        assert config.server == "imap.example.com"
        assert config.port == 993
        assert config.encryption == EncryptionMode.SSL_TLS
        assert config.on_fetch == OnFetch.MARK_READ
        assert config.fetch_interval == 300
        assert config.fetch_max == 10
        assert config.fetch_max_age_days == 1

    def test_default_encryption_inference(self):
        # Test standard ports with default encryption
        standard_ports = {
            143: EncryptionMode.STARTTLS,
            993: EncryptionMode.SSL_TLS,
        }

        for port, expected_encryption in standard_ports.items():
            config = IMAPConfig(
                username="user@example.com",
                password=SecretStr("password"),
                server="imap.example.com",
                port=port,
            )
            assert config.encryption == expected_encryption

    def test_non_standard_port_requires_encryption(self):
        # Test non-standard port requires explicit encryption
        with pytest.raises(ValidationError) as exc_info:
            IMAPConfig(
                username="user@example.com",
                password=SecretStr("password"),
                server="imap.example.com",
                port=1234,  # Non-standard port
            )
        assert "Cannot infer encryption mode" in str(exc_info.value)


class TestQueueSettings:
    def test_memory_queue_settings(self):
        # Test memory queue with defaults
        queue = MemoryQueueSettings()
        assert queue.queue_type == "Memory"
        assert queue.max_size == 0
        assert queue.timeout == 10

        # Test memory queue with custom values
        queue = MemoryQueueSettings(max_size=100, timeout=30)
        assert queue.queue_type == "Memory"
        assert queue.max_size == 100
        assert queue.timeout == 30

    def test_redis_queue_settings(self):
        # Test redis queue with minimal settings
        queue = RedisQueueSettings(key="test-queue")
        assert queue.queue_type == "Redis"
        assert queue.key == "test-queue"
        assert queue.host == "localhost"
        assert queue.port == 6379
        assert queue.db == 0
        assert queue.username is None
        assert queue.password is None
        assert queue.timeout == 10

        # Test redis queue with all settings
        queue = RedisQueueSettings(
            key="test-queue",
            host="redis.example.com",
            port=6380,
            db=1,
            username="redis-user",
            password="redis-password",
            timeout=30,
        )
        assert queue.queue_type == "Redis"
        assert queue.key == "test-queue"
        assert queue.host == "redis.example.com"
        assert queue.port == 6380
        assert queue.db == 1
        assert queue.username == "redis-user"
        assert queue.password == "redis-password"
        assert queue.timeout == 30


class TestWorkerPoolConfig:
    def test_worker_pool_defaults(self):
        # Test with defaults
        pool = WorkerPoolConfig()
        assert pool.worker_type == WorkerType.THREAD
        assert pool.count == 4

    def test_worker_pool_custom(self):
        # Test with custom values
        pool = WorkerPoolConfig(worker_type=WorkerType.PROCESS, count=8)
        assert pool.worker_type == WorkerType.PROCESS
        assert pool.count == 8


class TestRateLimitConfig:
    def test_rate_limit_config(self):
        # Test with valid values
        rate_limit = RateLimitConfig(limit=100, window="1 hour")
        assert rate_limit.limit == 100
        assert rate_limit.window == "1 hour"
        assert rate_limit._window_timedelta == datetime.timedelta(hours=1)

        # Test with different time format
        rate_limit = RateLimitConfig(limit=50, window="30 minutes")
        assert rate_limit.limit == 50
        assert rate_limit.window == "30 minutes"
        assert rate_limit._window_timedelta == datetime.timedelta(minutes=30)

    def test_invalid_window_format(self):
        # Test with invalid window format
        with pytest.raises(ValueError):
            RateLimitConfig(limit=100, window="invalid format")


class TestFilterHeaderConfig:
    def test_filter_header_config(self):
        # Test with defaults
        header_filter = FilterHeaderConfig(header="X-Custom-Header")
        assert header_filter.header == "X-Custom-Header"
        assert header_filter.values == []
        assert header_filter.mode == FilterMode.ALLOWLIST
        assert header_filter.verify == VerifyMode.ALWAYS

        # Test with custom values
        header_filter = FilterHeaderConfig(
            header="X-Custom-Header",
            values=["value1", "value2"],
            mode=FilterMode.DENYLIST,
            verify=VerifyMode.NEVER,
        )
        assert header_filter.header == "X-Custom-Header"
        assert header_filter.values == ["value1", "value2"]
        assert header_filter.mode == FilterMode.DENYLIST
        assert header_filter.verify == VerifyMode.NEVER


class TestSecurityConfig:
    def test_security_config_defaults(self):
        # Test with defaults
        security = SecurityConfig()
        assert security.rate_limit.limit == 100
        assert security.rate_limit.window == "1 day"
        assert security.rate_limit_per_sender is None
        assert security.rate_limit_per_domain is None
        assert security.allow_from == []
        assert security.allow_from_all_i_want_to_spend_it_all is False
        assert security.block_from is None
        assert security.filter_headers is None
        assert security.verify_dkim == VerifyMode.NEVER
        assert security.verify_mail_from == VerifyMode.NEVER
        assert security.verify_x_mail_from == VerifyMode.NEVER

    def test_security_config_custom(self):
        # Test with custom values
        security = SecurityConfig(
            rate_limit=RateLimitConfig(limit=200, window="2 hours"),
            rate_limit_per_sender=RateLimitConfig(limit=50, window="1 hour"),
            rate_limit_per_domain=RateLimitConfig(limit=100, window="1 day"),
            allow_from=["user1@example.com", "user2@example.com"],
            allow_from_all_i_want_to_spend_it_all=True,
            block_from=["spammer@example.com"],
            filter_headers=[
                FilterHeaderConfig(
                    header="X-Custom-Header",
                    values=["value1", "value2"],
                    mode=FilterMode.ALLOWLIST,
                )
            ],
            verify_dkim=VerifyMode.IF_PRESENT,
            verify_mail_from=VerifyMode.ALWAYS,
            verify_x_mail_from=VerifyMode.IF_PRESENT,
        )
        assert security.rate_limit.limit == 200
        assert security.rate_limit.window == "2 hours"
        assert security.rate_limit_per_sender is not None
        assert security.rate_limit_per_sender.limit == 50
        assert security.rate_limit_per_sender.window == "1 hour"
        assert security.rate_limit_per_domain is not None
        assert security.rate_limit_per_domain.limit == 100
        assert security.rate_limit_per_domain.window == "1 day"
        assert security.allow_from == ["user1@example.com", "user2@example.com"]
        assert security.allow_from_all_i_want_to_spend_it_all is True
        assert security.block_from == ["spammer@example.com"]
        assert security.filter_headers is not None
        assert len(security.filter_headers) == 1
        assert security.filter_headers[0].header == "X-Custom-Header"
        assert security.verify_dkim == VerifyMode.IF_PRESENT
        assert security.verify_mail_from == VerifyMode.ALWAYS
        assert security.verify_x_mail_from == VerifyMode.IF_PRESENT


class TestChatModelConfig:
    def test_chat_model_config_defaults(self):
        # Test with defaults
        config = ChatModelConfig()
        assert config.model is None
        assert config.model_provider is None
        assert config.max_tokens == 1024
        assert config.temperature == 0.2

    def test_chat_model_config_custom(self):
        # Test with custom values
        config = ChatModelConfig(
            model="gpt-4",
            model_provider="openai",
            max_tokens=2048,
            temperature=0.7,
            custom_param="custom_value",  # Extra param allowed
        )
        assert config.model == "gpt-4"
        assert config.model_provider == "openai"
        assert config.max_tokens == 2048
        assert config.temperature == 0.7
        assert config.model_dump()["custom_param"] == "custom_value"

    def test_chat_model_config_method(self):
        # Test chat_model_config method
        config = ChatModelConfig(
            model="gpt-4",
            model_provider="openai",
            max_tokens=2048,
            temperature=0.7,
            customParam="custom_value",  # Camel case param
        )
        model_config = config.chat_model_config()
        assert model_config["model"] == "gpt-4"
        assert model_config["model_provider"] == "openai"
        assert model_config["max_tokens"] == 2048
        assert model_config["temperature"] == 0.7
        assert model_config["custom_param"] == "custom_value"  # Converted to snake case


# Test-specific subclass of ModelSpec
class IsolatedModelSettings(ModelSpec, IsolatedRootSettings):
    """ModelSpec subclass for testing that doesn't load external config."""

    pass


class TestModelSpec:
    def test_model_spec_with_address(self):
        # Test with email address
        model = IsolatedModelSettings(
            name="Test Model",
            address="bot@example.com",
            system_prompt="You are a helpful assistant.",
            max_input_length=10000,
            params=ChatModelConfig(
                model="gpt-4",
                temperature=0.5,
            ),
        )
        assert model.name == "Test Model"
        assert model.address == "bot@example.com"
        assert model.address_regex is None
        assert model.system_prompt == "You are a helpful assistant."
        assert model.max_input_length == 10000
        assert model.params.model == "gpt-4"
        assert model.params.temperature == 0.5

    def test_model_spec_with_regex(self):
        # Test with address regex
        model = IsolatedModelSettings(
            name="Test Model",
            address_regex=r"bot-(?P<model>\w+)@example\.com",
            system_prompt="You are a helpful assistant.",
        )
        assert model.name == "Test Model"
        assert model.address is None
        assert model.address_regex == r"bot-(?P<model>\w+)@example\.com"
        assert model._address_regex is not None
        assert model.system_prompt == "You are a helpful assistant."

    def test_model_spec_missing_address(self):
        # Test with neither address nor regex
        with pytest.raises(ValidationError) as exc_info:
            IsolatedModelSettings(
                name="Test Model",
                system_prompt="You are a helpful assistant.",
            )
        assert "exactly one of Address or AddressRegex must be set" in str(exc_info.value)

    def test_model_spec_both_address_types(self):
        # Test with both address and regex
        with pytest.raises(ValidationError) as exc_info:
            IsolatedModelSettings(
                name="Test Model",
                address="bot@example.com",
                address_regex=r"bot-\w+@example\.com",
                system_prompt="You are a helpful assistant.",
            )
        assert "exactly one of Address or AddressRegex must be set" in str(exc_info.value)

    def test_invalid_regex(self):
        # Test with invalid regex
        with pytest.raises(ValidationError) as exc_info:
            IsolatedModelSettings(
                name="Test Model",
                address_regex=r"bot-(?P<model>\w+@example\.com",  # Missing closing parenthesis
                system_prompt="You are a helpful assistant.",
            )
        assert "invalid regex" in str(exc_info.value)

    def test_chat_model_config_with_regex_match(self):
        # Test chat_model_config with regex match
        model = IsolatedModelSettings(
            name="Test Model",
            address_regex=r"bot-(?P<model>\w+)@example\.com",
            system_prompt="You are a helpful assistant.",
            params=ChatModelConfig(
                temperature=0.5,
            ),
        )

        # Test with matching email
        config = model.chat_model_config(email_addr="bot-gpt4@example.com")
        assert config["temperature"] == 0.5
        assert config["model"] == "gpt4"  # Extracted from regex

        # Test with non-matching email
        config = model.chat_model_config(email_addr="other@example.com")
        assert config["temperature"] == 0.5
        assert config.get("model") is None  # No match, so no model extracted


# Test-specific subclass of ReplyConfig
class IsolatedReplySettings(ReplyConfig, IsolatedRootSettings):
    """ReplyConfig subclass for testing that doesn't load external config."""

    pass


class TestReplyConfig:
    def test_reply_config(self):
        # Test with valid models
        config = IsolatedReplySettings(
            models=[
                ModelSpec(
                    name="Model 1",
                    address="bot1@example.com",
                    system_prompt="You are bot 1.",
                ),
                ModelSpec(
                    name="Model 2",
                    address="bot2@example.com",
                    system_prompt="You are bot 2.",
                ),
            ],
            chat_model_configurable_fields={"Temperature", "MaxTokens"},
        )
        assert len(config.models) == 2
        assert config.models[0].name == "Model 1"
        assert config.models[1].name == "Model 2"
        assert config.chat_model_configurable_fields == {"temperature", "max_tokens"}

    def test_duplicate_addresses(self):
        # Test with duplicate addresses
        with pytest.raises(ValidationError) as exc_info:
            IsolatedReplySettings(
                models=[
                    ModelSpec(
                        name="Model 1",
                        address="bot@example.com",
                        system_prompt="You are bot 1.",
                    ),
                    ModelSpec(
                        name="Model 2",
                        address="bot@example.com",  # Duplicate address
                        system_prompt="You are bot 2.",
                    ),
                ],
            )
        assert "Each mailbot must use a unique email address" in str(exc_info.value)


# Test-specific subclass of FetchConfig
class IsolatedFetchSettings(FetchConfig, IsolatedRootSettings):
    """FetchConfig subclass for testing that doesn't load external config."""

    pass


class TestFetchConfig:
    def test_fetch_config(self):
        # Test with valid IMAP config
        config = IsolatedFetchSettings(
            imap=IMAPConfig(
                username="user@example.com",
                password=SecretStr("password"),
                server="imap.example.com",
            ),
            security=SecurityConfig(),
            receive_queue=MemoryQueueSettings(max_size=100),
            worker_pool=WorkerPoolConfig(count=2),
        )
        assert config.imap.username == "user@example.com"
        assert config.imap.password.get_secret_value() == "password"
        assert config.imap.server == "imap.example.com"
        assert config.imap.port == 993  # Default
        assert config.imap.encryption == EncryptionMode.SSL_TLS  # Inferred
        assert config.receive_queue.queue_type == "Memory"
        assert config.receive_queue.max_size == 100
        assert config.worker_pool.count == 2


# Test-specific subclass of SendConfig
class IsolatedSendSettings(SendConfig, IsolatedRootSettings):
    """SendConfig subclass for testing that doesn't load external config."""

    pass


class TestSendConfig:
    def test_send_config(self):
        # Test with valid SMTP config
        config = IsolatedSendSettings(
            smtp=SMTPConfig(
                username="user@example.com",
                password=SecretStr("password"),
                server="smtp.example.com",
            ),
            send_queue=MemoryQueueSettings(max_size=100),
            worker_pool=WorkerPoolConfig(count=2),
        )
        assert config.smtp.username == "user@example.com"
        assert config.smtp.password.get_secret_value() == "password"
        assert config.smtp.server == "smtp.example.com"
        assert config.smtp.port == 465  # Default
        assert config.smtp.encryption == EncryptionMode.SSL_TLS  # Inferred
        assert config.send_queue.queue_type == "Memory"
        assert config.send_queue.max_size == 100
        assert config.worker_pool.count == 2
