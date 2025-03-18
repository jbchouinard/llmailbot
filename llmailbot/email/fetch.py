import abc
import datetime
import email
from ssl import SSLContext
from typing import Iterator

from imap_tools.mailbox import BaseMailBox, MailBox, MailBoxTls, MailBoxUnencrypted
from imap_tools.message import MailMessage
from imap_tools.query import AND
from loguru import logger

from llmailbot.config import EncryptionMode, IMAPConfig, OnFetch
from llmailbot.email.model import MailQueue, SimpleEmail
from llmailbot.security import SecurityFilter
from llmailbot.taskrun import SyncTask, TaskDone

MAILBOX_CLS = {
    EncryptionMode.NONE: MailBoxUnencrypted,
    EncryptionMode.STARTTLS: MailBoxTls,
    EncryptionMode.SSL_TLS: MailBox,
}


# Monkey patch MailMessage to preserve the raw message data
# we need it for DKIM verification
def __init__(self, fetch_data: list):  # noqa: N807
    raw_message_data, raw_uid_data, raw_flag_data = self._get_message_data_parts(fetch_data)
    self._raw_uid_data = raw_uid_data
    self._raw_flag_data = raw_flag_data
    self._raw_message_data = raw_message_data
    self.obj = email.message_from_bytes(raw_message_data)


MailMessage.__init__ = __init__


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


class IMAPFetcher(abc.ABC):
    def __init__(self, config: IMAPConfig):
        self.config = config

    def make_query(self, only_unseen: bool = False):
        min_date = datetime.date.today() - datetime.timedelta(self.config.fetch_max_age_days)
        if only_unseen:
            return AND(seen=False, date_gte=min_date)
        else:
            return AND(date_gte=min_date)

    @abc.abstractmethod
    def fetch_messages(self) -> Iterator[SimpleEmail]:
        pass


class MarkReadFetcher(IMAPFetcher):
    """
    Download unread messages and mark them as read.
    """

    def fetch_messages(self) -> Iterator[SimpleEmail]:
        with connect_mailbox(self.config) as mailbox:
            q = self.make_query(only_unseen=True)
            logger.trace("Fetching mail with query: {}", q)
            for message in mailbox.fetch(q, bulk=self.config.fetch_max, mark_seen=True):
                if message.uid is None:
                    logger.warning("Message must have a UID")
                    continue
                yield SimpleEmail.from_message(message)


class DeleteFetcher(IMAPFetcher):
    """
    Download all messages and delete them.
    """

    def fetch_messages(self) -> Iterator[SimpleEmail]:
        with connect_mailbox(self.config) as mailbox:
            q = self.make_query(only_unseen=False)
            logger.debug("Fetching mail with query: {}", q)
            for message in mailbox.fetch(q, bulk=self.config.fetch_max, mark_seen=False):
                if message.uid is None:
                    logger.warning("Message must have a UID")
                    continue
                yield SimpleEmail.from_message(message)
                mailbox.delete(message.uid)


def make_mail_fetcher(config: IMAPConfig) -> IMAPFetcher:
    if config.on_fetch == OnFetch.MARK_READ:
        return MarkReadFetcher(config)
    elif config.on_fetch == OnFetch.DELETE:
        return DeleteFetcher(config)
    else:
        raise ValueError(f"Unknown fetch mode: {config.on_fetch}")


class FetchMailTask(SyncTask[None]):
    def __init__(
        self,
        fetcher: IMAPFetcher,
        queue: MailQueue,
        sec_filter: SecurityFilter | None = None,
    ):
        super().__init__(name=f"FetchMail<{fetcher.config.username}@{fetcher.config.server}>")
        self.fetcher = fetcher
        self.mailq = queue
        self.sec_filter = sec_filter

    def on_task_exception(self, exc: Exception):
        logger.exception("Exception in mail fetch task {}", self._name, exc_info=exc)

    def run(self) -> TaskDone | None:
        n = 0
        for n, s_email in enumerate(self.fetcher.fetch_messages(), 1):  # noqa: B007
            logger.info("Received {}", s_email.summary())
            if self.sec_filter:
                s_email = self.sec_filter.apply(s_email)
            if s_email:
                self.mailq.put(s_email)
        logger.debug("Fetched {} messages", n)
