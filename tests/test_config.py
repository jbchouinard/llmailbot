import pytest
from pydantic import ValidationError

from jbmailbot.config import AppConfig, EncryptionMode, IMAPConfig, SMTPConfig


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
    config = AppConfig(
        MailBots=[{"Name": "Test Chatbot", "IMAP": imap_config_dict, "SMTP": smtp_config_dict}]  # pyright: ignore[reportArgumentType]
    )
    assert config.mail_bots[0].name == "Test Chatbot"
