import functools
import sys

import aiorun
import click
from loguru import logger

from llmailbot.config import LLMailBotConfig
from llmailbot.core import run_app
from llmailbot.logging import LogLevel, setup_logging


def handle_cli_exceptions(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            click.echo(f"Error: {str(e)}", err=True)
            sys.exit(1)

    return wrapper


@click.command()
@click.option("--config", "config_file", default=None, help="Configuration file (default: None)")
@click.option("--log-level", type=str, default=LogLevel.INFO, help="Log level (default: INFO)")
@click.option("--log-file", default=None, help="Log file (default: stderr)")
@handle_cli_exceptions
def main(
    config_file: str | None,
    log_level: str,
    log_file: str | None,
):
    setup_logging(log_file, log_level)

    if config_file:
        LLMailBotConfig.model_config["yaml_file"] = config_file
    app_config = LLMailBotConfig()  # pyright: ignore[reportCallIssue]

    logger.debug(
        "Loaded config: {config}", config=app_config.model_dump_json(by_alias=True, indent=2)
    )
    aiorun.run(run_app(app_config))


if __name__ == "__main__":
    main()
