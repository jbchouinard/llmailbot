import asyncio
from ssl import SSLContext
from typing import Any, Awaitable, Callable, cast, override

from imap_tools.mailbox import BaseMailBox, MailBox, MailBoxTls, MailBoxUnencrypted
from imap_tools.query import AND
from loguru import logger

from llmailbot.config import EncryptionMode, IMAPConfig, SecurityConfig
from llmailbot.email.model import IMAPRawMessage
from llmailbot.queue.core import (
    AsyncQueue,
    SyncQueue,
    to_async_queue,
)
from llmailbot.security import Action, SecurityFilter, make_security_filter
from llmailbot.taskrun import AsyncTask, SyncTask

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
    mailbox.login(
        config.username, config.password.get_secret_value(), initial_folder=config.watch_folder
    )
    mailbox.email_message_class = IMAPRawMessage.from_fetch  # pyright: ignore[reportAttributeAccessIssue]
    return mailbox


class MailboxWatcher(AsyncTask):
    """
    Long-lived watcher for an IMAP mailbox folder.
    """

    def __init__(
        self,
        config: IMAPConfig,
        callback: Callable[[BaseMailBox, IMAPRawMessage], Awaitable[Any]],
        ssl_context: SSLContext | None = None,
        timeout: int | None = None,
    ):
        super().__init__()
        self.config = config
        self.ssl_context = ssl_context
        self.timeout = timeout
        self.folder_delim = None
        self.move_to_folder = None
        self.blocked_folder = None
        self.mb = connect_mailbox(self.config, self.ssl_context, self.timeout)
        self.setup_folders()
        self.callback = callback
        self.uids = []

    async def fetch_next_uid(self) -> IMAPRawMessage | None:
        next_uid = self.uids.pop()
        logger.trace("Fetching message with UID {}", next_uid)
        messages_iter = await asyncio.to_thread(self.mb.fetch, AND(uid=next_uid))
        messages = cast(list[IMAPRawMessage], list(messages_iter))
        if not messages:
            logger.warning("Failed to fetch message with UID {}", next_uid)
            return
        if len(messages) > 1:
            logger.warning("Multiple messages found with UID {}", next_uid)
        message = messages[0]
        message.uid = next_uid
        return message

    @override
    async def run(self):
        # Keep fetching the UIDs we already have before polling for new ones
        if self.uids:
            message = await self.fetch_next_uid()
            if message is not None:
                logger.trace("Callback processing message with UID {}", message.uid)
                await self.callback(self.mb, message)
            return

        new_messages = self.mb.folder.status().get("MESSAGES", 0)
        logger.trace("New messages count: {}", new_messages)
        if new_messages > 0:
            new_uids = await asyncio.to_thread(self.mb.uids)
            self.uids.extend(new_uids)
            logger.trace("Fetched {} new uids", len(self.uids))
        else:
            logger.trace("No new messages, IDLE for {} seconds", self.config.idle_timeout)
            # IDLE timeout doesn't play well with asyncio
            # TODO: find solution to use IDLE without hanging the process or
            # messing up the IMAP client states
            await asyncio.sleep(self.config.idle_timeout)
            # await asyncio.to_thread(self.mb.idle.wait, self.config.idle_timeout)
            return

    @override
    def on_cancelled(self):
        try:
            # Safely close the mailbox connection
            # Don't try to stop IDLE explicitly as it may cause state issues
            logger.debug("Logging out from mailbox")
            self.mb.logout()
        except Exception as e:
            logger.error("Error during mailbox cleanup: {}", str(e))

    @override
    def handle_exception(self, exc: Exception):
        try:
            # Safely close the mailbox connection
            # Don't try to stop IDLE explicitly as it may cause state issues
            logger.exception("Logging out from mailbox due to exception", exc_info=exc)
            self.mb.logout()
        except Exception as e:
            logger.exception("Error during mailbox cleanup after exception", exc_info=e)
        raise exc

    def setup_folders(self):
        if self.folder_delim is None:
            self.folder_delim = self.mb.folder.list(self.config.watch_folder)[0].delim
            if self.config.replied_folder:
                self.move_to_folder = self.config.replied_folder.replace("/", self.folder_delim)
            if self.config.blocked_folder:
                self.blocked_folder = self.config.blocked_folder.replace("/", self.folder_delim)

        if self.config.replied_folder:
            if not self.mb.folder.list(self.config.replied_folder):
                self.mb.folder.create(self.config.replied_folder)
        if self.config.blocked_folder:
            if not self.mb.folder.list(self.config.blocked_folder):
                self.mb.folder.create(self.config.blocked_folder)


def move_or_delete(mb: BaseMailBox, uid: str | list[str], folder: str | None):
    if folder:
        mb.move(uid, folder)
    else:
        mb.delete(uid)


def filter_and_enqueue(
    q: AsyncQueue[IMAPRawMessage],
    secf: SecurityFilter | None,
    replied_folder: str | None,
    blocked_folder: str | None,
) -> Callable[[BaseMailBox, IMAPRawMessage], Awaitable[None]]:
    if secf is None:

        async def qcallback(mb: BaseMailBox, message: IMAPRawMessage):
            await q.put(message)
            move_or_delete(mb, cast(str, message.uid), replied_folder)
    else:

        async def qcallback(mb: BaseMailBox, message: IMAPRawMessage):
            res = secf.apply(message.parsed())
            if res == Action.ALLOW:
                await q.put(message)
                move_or_delete(mb, cast(str, message.uid), replied_folder)
            else:
                move_or_delete(mb, cast(str, message.uid), blocked_folder)

    return qcallback


def make_mail_fetch_task(
    config: IMAPConfig,
    sec_config: SecurityConfig,
    queue: SyncQueue[IMAPRawMessage] | AsyncQueue[IMAPRawMessage],
) -> AsyncTask[None] | SyncTask[None]:
    return MailboxWatcher(
        config,
        callback=filter_and_enqueue(
            to_async_queue(queue),
            make_security_filter(sec_config),
            config.replied_folder,
            config.blocked_folder,
        ),
    )
