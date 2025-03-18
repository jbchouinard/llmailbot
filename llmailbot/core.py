import asyncio

from loguru import logger

from llmailbot.config import ConfigError, LLMailBotConfig
from llmailbot.email.fetch import FetchMailTask, make_mail_fetcher
from llmailbot.email.send import SendMailTask, make_mail_sender
from llmailbot.mailbot import BotReplySpawnTask, make_mailbot
from llmailbot.queue import make_queue
from llmailbot.security import make_security_filter
from llmailbot.taskrun import make_executor


async def run_app(config: LLMailBotConfig):
    if not config.models:
        raise ConfigError("No LLM model configured")

    awaitables = []

    executor = make_executor(config.worker_pool)

    mail_in_q = make_queue(config.queues)
    mail_out_q = make_queue(config.queues)

    mail_fetch_task = FetchMailTask(
        make_mail_fetcher(config.imap),
        mail_in_q,
        make_security_filter(config.security),
    )

    logger.debug("Starting mail fetcher: {}", mail_fetch_task._name)
    awaitables.append(
        mail_fetch_task.runner(executor).start(interval=config.imap.fetch_interval).wait()
    )

    mailbot_spawn_task = BotReplySpawnTask(
        make_mailbot(
            config.models,
            configurable_fields=config.chat_model_configurable_fields,
        ),
        mail_in_q,
        mail_out_q,
    )
    logger.debug("Starting mailbot spawn: {}", mailbot_spawn_task._name)
    awaitables.append(mailbot_spawn_task.runner().start().wait())

    mail_send_task = SendMailTask(
        make_mail_sender(config.smtp),
        mail_out_q,
    )
    logger.debug("Starting mail sender: {}", mail_send_task._name)
    awaitables.append(mail_send_task.runner(executor).start().wait())

    logger.success("All tasks started")
    await asyncio.gather(*awaitables)
