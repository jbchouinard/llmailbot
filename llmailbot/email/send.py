import abc
import asyncio
from smtplib import SMTP, SMTP_SSL
from ssl import SSLContext
from typing import Iterable

from loguru import logger

from llmailbot.config import EncryptionMode, SMTPConfig
from llmailbot.email.model import SimpleEmailMessage
from llmailbot.queue.core import AsyncQueue, SyncQueue, to_async_queue
from llmailbot.taskrun import AsyncTask, TaskDone


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
    def send(self, emails: Iterable[SimpleEmailMessage]) -> None:
        pass


class SMTPSender(MailSender):
    def send(self, emails: Iterable[SimpleEmailMessage]) -> None:
        with connect_smtp(self.smtp_config) as client:
            for email in emails:
                msg = email.to_email_message()
                client.send_message(
                    msg=msg,
                    from_addr=email.addr_from.email,
                    to_addrs=[a.email for a in email.addrs_to],
                )
                client.quit()


class StdoutFakeMailSender(MailSender):
    def send(self, email: SimpleEmailMessage) -> None:
        print(str(email))


class SendMailTask(AsyncTask[None]):
    def __init__(self, sender: MailSender, queue: AsyncQueue[SimpleEmailMessage]):
        super().__init__(
            name=f"SendMail<{sender.smtp_config.username}@{sender.smtp_config.server}>"
        )
        self.name = self._name
        self.sender = sender
        self.mailq = queue

    async def run(self) -> TaskDone | None:
        # TODO: implement batching to avoid re-connecting for every email
        email = await self.mailq.get()
        if email:
            await asyncio.get_running_loop().run_in_executor(
                None, lambda: self.sender.send([email])
            )
            logger.success("Sent {}", email.summary())


def make_mail_sender(config: SMTPConfig) -> MailSender:
    return SMTPSender(config)


def make_mail_send_task(
    config: SMTPConfig,
    queue: AsyncQueue[SimpleEmailMessage] | SyncQueue[SimpleEmailMessage],
):
    sender = make_mail_sender(config)
    return SendMailTask(sender, to_async_queue(queue))
