import abc
import datetime
from ssl import SSLContext
from typing import Iterator

from imap_tools.mailbox import BaseMailBox, MailBox, MailBoxTls, MailBoxUnencrypted
from imap_tools.query import AND
from loguru import logger

from llmailbot.config import EncryptionMode, IMAPConfig, MailFetchConfig, OnFetch
from llmailbot.email.model import MailQueue, SimpleEmail
from llmailbot.security import SecurityFilter
from llmailbot.taskrun import SyncTask, TaskDone

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
    def __init__(self, config: MailFetchConfig):
        self.config = config
        self.imap_config = config.imap

    def make_query(self, only_unseen: bool = False):
        min_date = datetime.date.today() - datetime.timedelta(self.config.max_age_days)
        if only_unseen:
            return AND(seen=False, date_gte=min_date)
        else:
            return AND(date_gte=min_date)

    @abc.abstractmethod
    def fetch_messages(self) -> Iterator[SimpleEmail]:
        pass


class MarkReadFetcher(MailFetcher):
    """
    Download unread messages and mark them as read.
    """

    def fetch_messages(self) -> Iterator[SimpleEmail]:
        with connect_mailbox(self.imap_config) as mailbox:
            q = self.make_query(only_unseen=True)
            logger.trace("Fetching mail with query: {}", q)
            for message in mailbox.fetch(q, bulk=self.config.batch_size, mark_seen=True):
                if message.uid is None:
                    logger.warning("Message must have a UID")
                    continue
                yield SimpleEmail.from_message(message)


class DeleteFetcher(MailFetcher):
    """
    Download all messages and delete them.
    """

    def fetch_messages(self) -> Iterator[SimpleEmail]:
        with connect_mailbox(self.imap_config) as mailbox:
            q = self.make_query(only_unseen=False)
            logger.debug("Fetching mail with query: {}", q)
            for message in mailbox.fetch(q, bulk=self.config.batch_size, mark_seen=False):
                if message.uid is None:
                    logger.warning("Message must have a UID")
                    continue
                yield SimpleEmail.from_message(message)
                mailbox.delete(message.uid)


def make_mail_fetcher(config: MailFetchConfig) -> MailFetcher:
    if config.fetch_mode == OnFetch.MARK_READ:
        return MarkReadFetcher(config)
    elif config.fetch_mode == OnFetch.DELETE:
        return DeleteFetcher(config)
    else:
        raise ValueError(f"Unknown fetch mode: {config.fetch_mode}")


class FetchMailTask(SyncTask[None]):
    def __init__(
        self,
        fetcher: MailFetcher,
        queue: MailQueue,
        sec_filter: SecurityFilter | None = None,
    ):
        super().__init__(
            name=f"FetchMail<{fetcher.imap_config.username}@{fetcher.imap_config.server}>"
        )
        self.fetcher = fetcher
        self.mailq = queue
        self.sec_filter = sec_filter

    def on_task_exception(self, exc: Exception):
        logger.exception("Exception in mail fetch task {}", self._name, exc_info=exc)

    def run(self) -> TaskDone | None:
        n = 0
        for n, email in enumerate(self.fetcher.fetch_messages(), 1):  # noqa: B007
            logger.info("Received {}", email.summary())
            if self.sec_filter:
                email = self.sec_filter.apply(email)
            if email:
                self.mailq.put(email)
        logger.debug("Fetched {} messages", n)
