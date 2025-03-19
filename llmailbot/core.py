import asyncio
from enum import StrEnum
from typing import Any, Awaitable

from loguru import logger

from llmailbot.config import ConfigError, LLMailBotConfig
from llmailbot.email.fetch import make_mail_fetch_task
from llmailbot.email.model import IMAPRawMessage, SimpleEmailMessage
from llmailbot.email.send import make_mail_send_task
from llmailbot.mailbot import make_bot_reply_spawn_task
from llmailbot.queue import make_queue
from llmailbot.queue.core import AsyncQueue
from llmailbot.taskrun import make_executor


class AppComponent(StrEnum):
    FETCH = "Fetch"
    SEND = "Send"
    REPLY = "Reply"


async def run_app(config: LLMailBotConfig):
    if not config.models:
        raise ConfigError("No LLM model configured")

    awaitables: list[Awaitable[Any]] = []

    executor = make_executor(config.worker_pool)
    asyncio.get_running_loop().set_default_executor(executor)

    assert config.receive_queue
    assert config.send_queue
    mail_recv_q: AsyncQueue[IMAPRawMessage] = make_queue(config.receive_queue)
    mail_send_q: AsyncQueue[SimpleEmailMessage] = make_queue(config.send_queue)

    mail_fetch_task = make_mail_fetch_task(config.imap, config.security, mail_recv_q)
    logger.debug("Starting mail fetcher: {}", mail_fetch_task._name)
    awaitables.append(mail_fetch_task.runner().start(interval=config.imap.fetch_interval).result())

    mailbot_spawn_task = make_bot_reply_spawn_task(config, mail_recv_q, mail_send_q)
    logger.debug("Starting mailbot spawn: {}", mailbot_spawn_task._name)
    awaitables.append(mailbot_spawn_task.runner().start().result())

    mail_send_task = make_mail_send_task(config.smtp, mail_send_q)
    logger.debug("Starting mail sender: {}", mail_send_task._name)
    awaitables.append(mail_send_task.runner().start().result())

    logger.success("All tasks started")
    await asyncio.gather(*awaitables)
