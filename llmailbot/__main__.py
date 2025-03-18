import functools
import sys

import aiorun
import click

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


@click.group()
@click.option("--config", "config_file", default=None, help="Configuration file (default: None)")
@click.option("--log-level", type=str, default=LogLevel.INFO, help="Log level (default: INFO)")
@click.option("--log-file", default=None, help="Log file (default: stderr)")
@handle_cli_exceptions
def cli(config_file: str | None, log_level: str, log_file: str | None):
    setup_logging(log_file, log_level)
    if config_file:
        LLMailBotConfig.model_config["yaml_file"] = config_file


@cli.command()
@handle_cli_exceptions
def config():
    """
    Print loaded configuration in YAML format.
    """
    app_config = LLMailBotConfig()  # pyright: ignore[reportCallIssue]
    click.echo(app_config.dump_yaml())


@cli.command()
@handle_cli_exceptions
def start():
    """
    Start the mail bot.
    """
    app_config = LLMailBotConfig()  # pyright: ignore[reportCallIssue]
    aiorun.run(run_app(app_config))


if __name__ == "__main__":
    cli()
