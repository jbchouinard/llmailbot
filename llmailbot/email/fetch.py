import asyncio
import datetime
from ssl import SSLContext
from typing import Iterator, cast, override

from imap_tools.mailbox import BaseMailBox, MailBox, MailBoxTls, MailBoxUnencrypted
from imap_tools.query import AND
from loguru import logger

from llmailbot.config import EncryptionMode, IMAPConfig, OnFetch, SecurityConfig
from llmailbot.email.model import IMAPRawMessage
from llmailbot.queue.core import (
    AsyncQueue,
    SyncQueue,
    to_async_queue,
)
from llmailbot.security import Action, SecurityFilter, make_security_filter
from llmailbot.taskrun import AsyncTask, SyncTask, TaskDone

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
    mailbox.email_message_class = IMAPRawMessage.from_fetch  # pyright: ignore[reportAttributeAccessIssue]
    return mailbox


class IMAPFetcher:
    def __init__(self, config: IMAPConfig):
        self.config = config
        if config.on_fetch == OnFetch.MARK_READ:
            self.only_unseen = True
            self.mark_seen = True
        else:
            self.only_unseen = False
            self.mark_seen = False

    def make_query(self):
        min_date = datetime.date.today() - datetime.timedelta(self.config.fetch_max_age_days)
        if self.only_unseen:
            return AND(seen=False, date_gte=min_date)
        else:
            return AND(date_gte=min_date)

    def fetch_messages(self) -> Iterator[IMAPRawMessage]:
        with connect_mailbox(self.config) as mailbox:
            q = self.make_query()
            logger.debug("Fetching mail with query: {}", q)
            for message in mailbox.fetch(
                q,
                bulk=True,
                mark_seen=self.mark_seen,
                limit=self.config.fetch_max,
            ):
                if message.uid is None:
                    logger.warning("Message has no UID")
                    continue
                yield cast(IMAPRawMessage, message)
                if self.config.on_fetch == OnFetch.DELETE:
                    mailbox.delete(message.uid)


class FetchMailTask(AsyncTask[None]):
    def __init__(
        self,
        fetcher: IMAPFetcher,
        queue: AsyncQueue[IMAPRawMessage],
        sec_filter: SecurityFilter | None = None,
    ):
        super().__init__(name=f"FetchMail<{fetcher.config.username}@{fetcher.config.server}>")
        self.fetcher = fetcher
        self.mailq = queue
        self.sec_filter = sec_filter

    @override
    async def run(self) -> TaskDone | None:
        n = 0
        raw_emails = await asyncio.get_running_loop().run_in_executor(
            None, self.fetcher.fetch_messages
        )
        for n, raw_email in enumerate(raw_emails, 1):  # noqa: B007
            email = raw_email.parsed()
            logger.info("Received {}", email.summary())
            if self.sec_filter:
                action = self.sec_filter.apply(email)
                if action == Action.ALLOW:
                    await self.mailq.put(raw_email)
        logger.debug("Fetched {} messages", n)


def make_mail_fetch_task(
    config: IMAPConfig,
    sec_config: SecurityConfig,
    queue: SyncQueue[IMAPRawMessage] | AsyncQueue[IMAPRawMessage],
) -> AsyncTask[None] | SyncTask[None]:
    fetcher = IMAPFetcher(config)
    return FetchMailTask(fetcher, to_async_queue(queue), make_security_filter(sec_config))
