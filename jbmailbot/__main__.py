import asyncio
import functools
import sys

import aiorun
import click
from loguru import logger

from jbmailbot.config import AppConfig, MailBotConfig
from jbmailbot.email.fetch import FetchMailTask, make_mail_fetcher
from jbmailbot.email.model import SimpleEmail
from jbmailbot.email.send import SendMailTask, make_mail_sender
from jbmailbot.logging import LogLevel, setup_logging
from jbmailbot.mailbot import RunBotTask, make_mailbot
from jbmailbot.queue import AnyQueue, make_queue
from jbmailbot.runtask import make_executor


def handle_cli_exceptions(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            click.echo(f"Error: {str(e)}", err=True)
            sys.exit(1)

    return wrapper


async def run_bot(conf: MailBotConfig):
    send_queue: AnyQueue[SimpleEmail] = make_queue(
        conf.send.queue,
        conf.send.workers.concurrency_type,
    )
    sender = make_mail_sender(conf.send)
    send_executor = make_executor(conf.send.workers)
    send_runner = SendMailTask(sender, send_queue).runner(send_executor)

    fetch_queue: AnyQueue[SimpleEmail] = make_queue(
        conf.receive.queue,
        conf.receive.workers.concurrency_type,
    )
    fetcher = make_mail_fetcher(conf.receive)
    fetch_executor = make_executor(conf.receive.workers)
    fetch_runner = FetchMailTask(fetcher, fetch_queue).runner(fetch_executor)

    mailbot = make_mailbot(conf)
    mailbot_runner = RunBotTask(mailbot, recv_queue=fetch_queue, send_queue=send_queue).runner()

    fetch_runner.start(interval=conf.receive.fetch_interval)
    mailbot_runner.start()
    send_runner.start()
    await asyncio.gather(fetch_runner.wait(), mailbot_runner.wait(), send_runner.wait())


async def run_app(config: AppConfig):
    tasks = []
    for conf in config.mailbots:
        logger.info("Starting mailbot: {}", conf.name)
        tasks.append(run_bot(conf))

    logger.info("All mailbots started")
    await asyncio.gather(*tasks)


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
