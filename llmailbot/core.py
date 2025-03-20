import asyncio
from enum import StrEnum
from typing import Awaitable, Iterable

from loguru import logger

from llmailbot.config import ConfigError, FetchConfig, QueueSettings, ReplyConfig, SendConfig
from llmailbot.email.fetch import make_mail_fetch_task
from llmailbot.email.model import IMAPRawMessage, SimpleEmailMessage
from llmailbot.email.send import make_mail_send_task
from llmailbot.mailbot import make_bot_reply_spawn_task
from llmailbot.queue import make_queue
from llmailbot.queue.core import AsyncQueue
from llmailbot.taskrun import make_executor, run_in_background


class AppComponent(StrEnum):
    FETCH = "fetch"
    REPLY = "reply"
    SEND = "send"


_mail_recv_q: AsyncQueue[IMAPRawMessage] | None = None


def get_mail_recv_q(conf: QueueSettings | None) -> AsyncQueue[IMAPRawMessage]:
    global _mail_recv_q
    if conf is None:
        raise ConfigError("Receive queue not configured")
    if _mail_recv_q is None:
        _mail_recv_q = make_queue(conf)

    return _mail_recv_q


_mail_send_q: AsyncQueue[SimpleEmailMessage] | None = None


def get_mail_send_q(conf: QueueSettings | None) -> AsyncQueue[SimpleEmailMessage]:
    global _mail_send_q
    if conf is None:
        raise ConfigError("Send queue not configured")
    if _mail_send_q is None:
        _mail_send_q = make_queue(conf)

    return _mail_send_q


async def run_app(components: Iterable[AppComponent] | None = None):
    if not components:
        components = list(AppComponent)
    components = set(components)

    tasks: list[Awaitable[None]] = []

    if AppComponent.FETCH in components:
        fetch_conf = FetchConfig()  # pyright: ignore[reportCallIssue]
        executor = make_executor(fetch_conf.worker_pool)
        asyncio.get_running_loop().set_default_executor(executor)
        tasks.append(
            run_in_background(
                make_mail_fetch_task(
                    fetch_conf.imap,
                    fetch_conf.security,
                    get_mail_recv_q(fetch_conf.receive_queue),
                ),
                interval=fetch_conf.imap.fetch_interval,
                restart_delay=10,
                max_repeated_exc=5,
                max_repeated_exc_period=600,
                logger=logger,
            )
        )

    if AppComponent.REPLY in components:
        reply_conf = ReplyConfig()  # pyright: ignore[reportCallIssue]
        if not reply_conf.models:
            raise ConfigError("No LLM model configured")

        tasks.append(
            run_in_background(
                make_bot_reply_spawn_task(
                    reply_conf,
                    get_mail_recv_q(reply_conf.receive_queue),
                    get_mail_send_q(reply_conf.send_queue),
                ),
                max_repeated_exc=3,
                max_repeated_exc_period=10,
                restart_delay=1,
                logger=logger,
            )
        )

    if AppComponent.SEND in components:
        send_conf = SendConfig()  # pyright: ignore[reportCallIssue]
        # Due to how the configuration system is designed, if both SEND and FETCH are run,
        # they will have the same worker pool settings, and FETCH already created
        # the executor
        if AppComponent.FETCH not in components:
            executor = make_executor(send_conf.worker_pool)
            asyncio.get_running_loop().set_default_executor(executor)
        tasks.append(
            run_in_background(
                make_mail_send_task(
                    send_conf.smtp,
                    get_mail_send_q(send_conf.send_queue),
                ),
                restart_delay=10,
                max_repeated_exc=5,
                max_repeated_exc_period=600,
                logger=logger,
            )
        )

    logger.success("All tasks started")
    await asyncio.gather(*tasks)
