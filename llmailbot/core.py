import asyncio

from loguru import logger

from llmailbot.config import AppConfig, ConfigError
from llmailbot.email.fetch import FetchMailTask, make_mail_fetcher
from llmailbot.email.send import SendMailTask, make_mail_sender
from llmailbot.mailbot import BotReplySpawnTask, make_mailbot
from llmailbot.queue import make_queue
from llmailbot.security import make_security_filter
from llmailbot.taskrun import make_executor


async def run_app(config: AppConfig):
    if not config.mailbots:
        raise ConfigError("No mailbots configured")

    awaitables = []

    executor = make_executor(config.worker_pool)

    incoming_mail_q = make_queue(config.queues)
    outgoing_mail_q = make_queue(config.queues)

    mail_fetch_task = FetchMailTask(
        make_mail_fetcher(config.mailfetch),
        incoming_mail_q,
        make_security_filter(config.security),
    )

    logger.debug("Starting mail fetcher: {}", mail_fetch_task._name)
    awaitables.append(
        mail_fetch_task.runner(executor).start(interval=config.mailfetch.fetch_interval).wait()
    )

    mailbot_spawn_task = BotReplySpawnTask(
        make_mailbot(
            config.mailbots,
            configurable_fields=config.chat_model_configurable_fields,
        ),
        incoming_mail_q,
        outgoing_mail_q,
    )
    logger.debug("Starting mailbot spawn: {}", mailbot_spawn_task._name)
    awaitables.append(mailbot_spawn_task.runner().start().wait())

    mail_send_task = SendMailTask(
        make_mail_sender(config.mailsend),
        outgoing_mail_q,
    )
    logger.debug("Starting mail sender: {}", mail_send_task._name)
    awaitables.append(mail_send_task.runner(executor).start().wait())

    logger.success("All tasks started")
    await asyncio.gather(*awaitables)
