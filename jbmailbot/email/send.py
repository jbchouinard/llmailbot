import abc
from smtplib import SMTP, SMTP_SSL
from ssl import SSLContext

from loguru import logger

from jbmailbot.config import EncryptionMode, MailSendConfig, SMTPConfig
from jbmailbot.email.model import SimpleEmail
from jbmailbot.queue import AnyQueue
from jbmailbot.runtask import SyncTask, TaskDone


def connect_smtp(
    config: SMTPConfig,
    ssl_context: SSLContext | None = None,
    timeout: int = 30,
) -> SMTP | SMTP_SSL:
    if config.encryption == EncryptionMode.STARTTLS:
        client = SMTP(host=config.server, port=config.port, timeout=timeout)
        client.starttls(context=ssl_context)
    elif config.encryption == EncryptionMode.SSL_TLS:
        client = SMTP_SSL(
            host=config.server, port=config.port, timeout=timeout, context=ssl_context
        )
    else:
        client = SMTP(host=config.server, port=config.port, timeout=timeout)

    client.login(config.username, config.password.get_secret_value())
    return client


class MailSender(abc.ABC):
    def __init__(self, smtp_config: SMTPConfig):
        self.smtp_config = smtp_config

    @abc.abstractmethod
    def send(self, email: SimpleEmail) -> None:
        pass


class StdoutFakeMailSender(MailSender):
    def send(self, email: SimpleEmail) -> None:
        print(str(email))


def make_mail_sender(config: MailSendConfig) -> MailSender:
    return StdoutFakeMailSender(config.smtp)


class SendMailTask(SyncTask[None]):
    def __init__(self, sender: MailSender, queue: AnyQueue[SimpleEmail]):
        super().__init__(name=f"SendMail({sender.smtp_config.server})")
        self.sender = sender
        self.mailq = queue

    def on_task_exception(self, exc: Exception):
        logger.exception(f"Exception in mail send task {self.name}", exc_info=exc)

    def run(self) -> TaskDone | None:
        email = self.mailq.get(block=True, timeout=5)
        if email:
            self.sender.send(email)
            logger.info(f"Sent email {email.summary()}")
