import asyncio
import functools
import sys

import aiorun
import click
from loguru import logger

from jbmailbot.config import AppConfig
from jbmailbot.logging import LogLevel, setup_logging
from jbmailbot.mailbot import RunBotTask, make_mailbot
from jbmailbot.mailfetch import FetchMailTask, make_mail_fetcher
from jbmailbot.mailqueue import make_mail_queue
from jbmailbot.mailsend import make_mail_sender
from jbmailbot.runtask import TaskRunner, make_executor


def handle_cli_exceptions(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            click.echo(f"Error: {str(e)}", err=True)
            sys.exit(1)

    return wrapper


async def run_app(config: AppConfig):
    tasks: list[TaskRunner] = []
    for mailbot_conf in config.mailbots:
        logger.info("Starting mailbot: {}", mailbot_conf.name)
        recv_queue = make_mail_queue(
            mailbot_conf.receive.queue,
            mailbot_conf.receive.workers.concurrency_type,
        )
        sender = make_mail_sender(mailbot_conf.send)
        fetcher = make_mail_fetcher(mailbot_conf.receive)
        mail_fetch_executor = make_executor(mailbot_conf.receive.workers)
        mail_fetch_runner = FetchMailTask(fetcher, recv_queue).runner(mail_fetch_executor)
        mail_fetch_runner.start(interval=mailbot_conf.receive.fetch_interval)
        tasks.append(mail_fetch_runner)
        mailbot = make_mailbot(mailbot_conf)
        bot_runner = RunBotTask(mailbot, recv_queue, sender).runner()
        bot_runner.start(interval=None)
        tasks.append(bot_runner)

    logger.info("All mailbots started")
    await asyncio.gather(*(task.wait() for task in tasks))


@click.command()
@click.option("--config", "config_file", default=None, help="Configuration file (default: None)")
@click.option("--log-level", type=str, default=LogLevel.INFO, help="Log level (default: INFO)")
@click.option("--log-file", default=None, help="Log file (default: stderr)")
@handle_cli_exceptions
def main(config_file: str | None, log_level: str, log_file: str | None):
    setup_logging(log_file, log_level)

    if config_file:
        AppConfig.model_config["yaml_file"] = config_file
    app_config = AppConfig()  # pyright: ignore[reportCallIssue]

    logger.debug(
        "Loaded config: {config}", config=app_config.model_dump_json(by_alias=True, indent=2)
    )
    aiorun.run(run_app(app_config))


if __name__ == "__main__":
    main()
