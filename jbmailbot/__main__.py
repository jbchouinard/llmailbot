import functools
import sys

import click
from loguru import logger

from jbmailbot.config import AppConfig
from jbmailbot.logging import LogLevel, setup_logging


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
@click.option("--log-level", type=str, default=LogLevel.INFO, help="Log level (default: INFO)")
@click.option("--log-file", default=None, help="Log file (default: stderr)")
@handle_cli_exceptions
def main(log_level: str, log_file: str | None):
    setup_logging(log_file, log_level)
    config = AppConfig()  # pyright: ignore[reportCallIssue]
    logger.debug("Loaded config: {config}", config=config.model_dump_json(by_alias=True, indent=2))


if __name__ == "__main__":
    main()
