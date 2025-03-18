# pyright: reportCallIssue=false
import json
from pathlib import Path

import pytest
from pydantic import SecretStr, ValidationError

from llmailbot.config import (
    ChatModelConfig,
    IMAPConfig,
    LLMailBotConfig,
    ModelSpec,
    RateLimitConfig,
    SecurityConfig,
    SettingsConfigDict,
    SMTPConfig,
)
from llmailbot.enums import EncryptionMode, OnFetch, VerifyMode


def make_test_app_config_cls(
    env_file: str | None = None,
    secrets_dir: str | None = None,
    env_prefix="TEST_LLMAILBOT_TEST_",
    yaml_file: str | None = None,
):
    class TestAppConfig(LLMailBotConfig):
        model_config = SettingsConfigDict(
            env_file=env_file,
            secrets_dir=secrets_dir,
            env_nested_delimiter="__",
            env_prefix=env_prefix,
            case_sensitive=False,
            yaml_file=yaml_file,
        )

    return TestAppConfig


@pytest.mark.parametrize("value", ["starttls", "StartTLS", "STARTTLS"])
def test_case_insensitive_enum(value):
    assert EncryptionMode.STARTTLS == EncryptionMode(value)


@pytest.fixture
def smtp_config_dict():
    return {
        "Username": "chatbot@example.com",
        "Password": "my-secret-password",
        "Server": "smtp.example.com",
        "Port": 587,
    }


@pytest.fixture
def smtp_config(smtp_config_dict):
    return SMTPConfig.model_validate(smtp_config_dict)


@pytest.fixture
def imap_config_dict():
    return {
        "Username": "chatbot@example.com",
        "Password": "my-secret-password",
        "Server": "imap.example.com",
        "Port": 993,
    }


@pytest.fixture
def imap_config(imap_config_dict):
    return IMAPConfig.model_validate(imap_config_dict)


@pytest.mark.parametrize(
    ["port", "expected"],
    [(25, EncryptionMode.NONE), (587, EncryptionMode.STARTTLS), (465, EncryptionMode.SSL_TLS)],
)
def test_default_encryption_mode_smtp(smtp_config_dict, port, expected):
    smtp_config_dict["Port"] = port
    smtp_config = SMTPConfig.model_validate(smtp_config_dict)
    assert smtp_config.encryption == expected


def test_imap_non_standard_port_raises_error(imap_config_dict):
    imap_config_dict["Port"] = 1234
    with pytest.raises(ValidationError):
        IMAPConfig.model_validate(imap_config_dict)


def test_app_config(imap_config_dict, smtp_config_dict):
    app_config_cls = make_test_app_config_cls()

    # Create objects instead of dictionaries to satisfy type checking
    model_config = ChatModelConfig(
        model="gpt-4.5", model_provider="openai", max_tokens=2048, temperature=0.2
    )

    model_spec = ModelSpec(
        Name="Test Chatbot",
        Address="chatbot@example.com",
        AddressRegex=None,
        MaxInputLength=10000,
        SystemPrompt="You are a helpful assistant.",
        ChatModelConfig=model_config,
    )
    # Manually set the _address_regex field since it's set by a validator
    model_spec._address_regex = None

    imap_config = IMAPConfig(
        Mode=OnFetch.MARK_READ,
        Interval=60,
        MaxAgeDays=7,
        BatchSize=20,
        **imap_config_dict,
    )

    smtp_config = SMTPConfig(**smtp_config_dict)

    config = app_config_cls(
        Models=[model_spec],
        IMAP=imap_config,
        SMTP=smtp_config,
        ChatModelConfigurableFields=set(["model", "model_provider", "max_tokens", "temperature"]),
    )
    assert config.models[0].name == "Test Chatbot"


def test_app_config_from_secrets_dir(tmp_path: Path):
    # Create mailbot configuration
    model_params = ChatModelConfig(
        model="gpt-4.5", model_provider="openai", max_tokens=2048, temperature=0.2
    )

    model_conf = ModelSpec(
        Name="Test Chatbot",
        Address="chatbot@example.com",
        AddressRegex=None,
        MaxInputLength=10000,
        SystemPrompt="You are a helpful assistant.",
        ChatModelConfig=model_params,
    )
    # Manually set the _address_regex field since it's set by a validator
    model_conf._address_regex = None

    # Create mail fetch configuration
    imap_conf = IMAPConfig(
        Username="chatbot@example.com",
        Password=SecretStr("my-secret-password"),
        Server="imap.example.com",
        Port=993,
        Encryption=EncryptionMode.STARTTLS,
        OnFetch=OnFetch.MARK_READ,
        FetchInterval=60,
        FetchMaxAgeDays=7,
        FetchMax=100,
    )

    # Create mail send configuration
    smtp_conf = SMTPConfig(
        Username="chatbot@example.com",
        Password=SecretStr("my-secret-password"),
        Server="smtp.example.com",
        Port=587,
        Encryption=EncryptionMode.STARTTLS,
    )

    # Create security configuration
    security_conf = SecurityConfig(
        AllowFrom=["me@example.org"],
        BlockFrom=[],
        RateLimit=RateLimitConfig(Limit=100, Window="1 day"),
        RateLimitPerSender=None,
        RateLimitPerDomain=None,
        VerifyDKIM=VerifyMode.NEVER,
        VerifyMailFrom=VerifyMode.NEVER,
        VerifyXMailFrom=VerifyMode.NEVER,
    )

    # Write configurations to secret files
    with (tmp_path / "models").open("w") as f:
        json.dump([model_conf.model_dump(mode="json", by_alias=True)], f)

    with (tmp_path / "imap").open("w") as f:
        json.dump(imap_conf.model_dump(mode="json", by_alias=True), f)

    with (tmp_path / "smtp").open("w") as f:
        json.dump(smtp_conf.model_dump(mode="json", by_alias=True), f)

    with (tmp_path / "security").open("w") as f:
        json.dump(security_conf.model_dump(mode="json", by_alias=True), f)

    # Load configuration from secrets directory
    app_config_cls = make_test_app_config_cls(secrets_dir=tmp_path.as_posix())
    config = app_config_cls()  # pyright: ignore[reportCallIssue]

    # Assertions
    assert config.models[0].name == "Test Chatbot"
    assert config.security.allow_from == ["me@example.org"]
    assert config.imap.username == "chatbot@example.com"
    assert config.smtp.username == "chatbot@example.com"
