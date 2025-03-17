# pyright: reportCallIssue=false
import json
from pathlib import Path

import pytest
from pydantic import SecretStr, ValidationError

from llmailbot.config import (
    AppConfig,
    ChatModelConfig,
    FilterConfig,
    IMAPConfig,
    MailBotSpec,
    MailFetchConfig,
    MailSendConfig,
    SecurityConfig,
    SettingsConfigDict,
    SMTPConfig,
)
from llmailbot.enums import EncryptionMode, FilterMode, OnFetch


def make_test_app_config_cls(
    env_file: str | None = None,
    secrets_dir: str | None = None,
    env_prefix="TEST_LLMAILBOT_TEST_",
    yaml_file: str | None = None,
):
    class TestAppConfig(AppConfig):
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

    mailbot = MailBotSpec(
        Name="Test Chatbot",
        Address="chatbot@example.com",
        AddressRegex=None,
        MaxInputLength=10000,
        SystemPrompt="You are a helpful assistant.",
        ChatModelConfig=model_config,
    )
    # Manually set the _address_regex field since it's set by a validator
    mailbot._address_regex = None

    mail_fetch = MailFetchConfig(
        Mode=OnFetch.MARK_READ,
        Interval=60,
        MaxAgeDays=7,
        BatchSize=20,
        IMAP=IMAPConfig(**imap_config_dict),
    )

    mail_send = MailSendConfig(SMTP=SMTPConfig(**smtp_config_dict))

    config = app_config_cls(
        MailBots=[mailbot],
        MailFetch=mail_fetch,
        MailSend=mail_send,
        ChatModelConfigurableFields=set(["model", "model_provider", "max_tokens", "temperature"]),
    )
    assert config.mailbots[0].name == "Test Chatbot"


def test_app_config_from_secrets_dir(tmp_path: Path):
    # Create mailbot configuration
    model_config = ChatModelConfig(
        model="gpt-4.5", model_provider="openai", max_tokens=2048, temperature=0.2
    )

    mailbot_conf = MailBotSpec(
        Name="Test Chatbot",
        Address="chatbot@example.com",
        AddressRegex=None,
        MaxInputLength=10000,
        SystemPrompt="You are a helpful assistant.",
        ChatModelConfig=model_config,
    )
    # Manually set the _address_regex field since it's set by a validator
    mailbot_conf._address_regex = None

    # Create mail fetch configuration
    mail_fetch_conf = MailFetchConfig(
        Mode=OnFetch.MARK_READ,
        Interval=60,
        MaxAgeDays=7,
        BatchSize=100,
        IMAP=IMAPConfig(
            Username="chatbot@example.com",
            Password=SecretStr("my-secret-password"),
            Server="imap.example.com",
            Port=993,
            Encryption=EncryptionMode.STARTTLS,
        ),
    )

    # Create mail send configuration
    mail_send_conf = MailSendConfig(
        SMTP=SMTPConfig(
            Username="chatbot@example.com",
            Password=SecretStr("my-secret-password"),
            Server="smtp.example.com",
            Port=587,
            Encryption=EncryptionMode.STARTTLS,
        ),
    )

    # Create security configuration
    filter_config = FilterConfig(Mode=FilterMode.DENYLIST, Addresses=[])
    security_conf = SecurityConfig(
        FilterFrom=filter_config,
        RateLimit=None,
        RateLimitPerSender=None,
        RateLimitPerDomain=None,
        SecretKey=None,
        Workers=1,
    )

    # Write configurations to secret files
    with (tmp_path / "mailbots").open("w") as f:
        json.dump([mailbot_conf.model_dump(mode="json", by_alias=True)], f)

    with (tmp_path / "mailfetch").open("w") as f:
        json.dump(mail_fetch_conf.model_dump(mode="json", by_alias=True), f)

    with (tmp_path / "mailsend").open("w") as f:
        json.dump(mail_send_conf.model_dump(mode="json", by_alias=True), f)

    with (tmp_path / "security").open("w") as f:
        json.dump(security_conf.model_dump(mode="json", by_alias=True), f)

    # Load configuration from secrets directory
    app_config_cls = make_test_app_config_cls(secrets_dir=tmp_path.as_posix())
    config = app_config_cls()  # pyright: ignore[reportCallIssue]

    # Assertions
    assert config.mailbots[0].name == "Test Chatbot"
    assert config.security.filter_from.mode == FilterMode.DENYLIST
    assert config.security.filter_from.addresses == []
