from pathlib import Path

import pytest
from pydantic import ValidationError

from jbmailbot.config import (
    AppConfig,
    EncryptionMode,
    IMAPConfig,
    SecurityConfig,
    SecurityMode,
    SettingsConfigDict,
    SMTPConfig,
)


def test_app_config_cls(
    env_file: str | None = None,
    secrets_dir: str | None = None,
    env_prefix="TEST_JBMAILBOT_TEST_",
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
    app_config_cls = test_app_config_cls()
    config = app_config_cls(
        MailBots=[{"Name": "Test Chatbot", "IMAP": imap_config_dict, "SMTP": smtp_config_dict}]  # pyright: ignore[reportArgumentType]
    )
    assert config.mailbots[0].name == "Test Chatbot"


def test_app_config_from_secrets_dir(tmp_path: Path):
    security_conf = SecurityConfig(
        Addresses=[], Mode=SecurityMode.DENYLIST, RateLimit=None, RateLimitPerSender=None
    )
    security_json = security_conf.model_dump_json(by_alias=True)
    with (tmp_path / "security").open("w") as f:
        f.write(security_json)
    with (tmp_path / "mailbots").open("w") as f:
        f.write("[]")

    app_config_cls = test_app_config_cls(secrets_dir=tmp_path.as_posix())
    config = app_config_cls()  # pyright: ignore[reportCallIssue]
    assert config.security.mode == SecurityMode.DENYLIST
    assert config.security.addresses == []
    assert config.security.rate_limit is None
    assert config.security.rate_limit_per_sender is None
    assert config.mailbots == []
