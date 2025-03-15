import abc
from ssl import SSLContext
from typing import Iterator

from imap_tools.mailbox import BaseMailBox, MailBox, MailBoxTls, MailBoxUnencrypted
from imap_tools.message import MailMessage
from imap_tools.query import AND
from loguru import logger

from jbmailbot.config import EncryptionMode, FetchMode, IMAPConfig, MailFetchConfig
from jbmailbot.mailqueue import AnyQueue
from jbmailbot.runtask import SyncTask, TaskDone

MAILBOX_CLS = {
    EncryptionMode.NONE: MailBoxUnencrypted,
    EncryptionMode.STARTTLS: MailBoxTls,
    EncryptionMode.SSL_TLS: MailBox,
}


def connect_mailbox(
    config: IMAPConfig,
    ssl_context: SSLContext | None = None,
    timeout: int | None = None,
) -> BaseMailBox:
    kwargs = {
        "host": config.server,
        "port": config.port,
        "timeout": timeout,
    }
    if ssl_context is not None and config.encryption != EncryptionMode.NONE:
        kwargs["ssl_context"] = ssl_context

    if config.encryption is None:
        raise ValueError("Encryption mode cannot be None")
    cls: type[BaseMailBox] = MAILBOX_CLS[config.encryption]
    mailbox: BaseMailBox = cls(**kwargs)
    mailbox.login(config.username, config.password.get_secret_value())
    return mailbox


class MailFetcher(abc.ABC):
    def __init__(self, imap_config: IMAPConfig):
        self.imap_config = imap_config

    @abc.abstractmethod
    def fetch_messages(self) -> Iterator[MailMessage]:
        pass


class MarkReadFetcher(MailFetcher):
    """
    Download unread messages and mark them as read.
    """

    def fetch_messages(self):
        with connect_mailbox(self.imap_config) as mailbox:
            for message in mailbox.fetch(AND(seen=False), bulk=10, mark_seen=True):
                if message.uid is None:
                    logger.warning("Message must have a UID")
                    continue
                yield message


class DeleteFetcher(MailFetcher):
    """
    Download all messages and delete them.
    """

    def fetch_messages(self):
        with connect_mailbox(self.imap_config) as mailbox:
            for message in mailbox.fetch(bulk=10, mark_seen=False):
                if message.uid is None:
                    logger.warning("Message must have a UID")
                    continue
                yield message
                mailbox.delete(message.uid)


def make_mail_fetcher(config: MailFetchConfig) -> MailFetcher:
    if config.fetch_mode == FetchMode.MARK_READ:
        return MarkReadFetcher(config.imap)
    elif config.fetch_mode == FetchMode.DELETE:
        return DeleteFetcher(config.imap)
    else:
        raise ValueError(f"Unknown fetch mode: {config.fetch_mode}")


class FetchMailTask(SyncTask[None]):
    def __init__(self, fetcher: MailFetcher, queue: AnyQueue[MailMessage]):
        super().__init__(name=f"FetchMail({fetcher.imap_config.server})")
        self.fetcher = fetcher
        self.mailq = queue

    def on_task_exception(self, exc: Exception):
        logger.exception(f"Exception in mail fetch task {self.name}", exc_info=exc)

    def run(self) -> TaskDone | None:
        n = 0
        for n, message in enumerate(self.fetcher.fetch_messages(), 1):  # noqa: B007
            logger.debug(
                "Received message uid={}, id={}, from {}",
                message.uid,
                message.obj.get("Message-Id"),
                message.from_,
            )
            self.mailq.put(message)
        logger.debug(f"Fetched {n} messages")
