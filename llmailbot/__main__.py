# pyright: reportCallIssue=false
import functools
import sys

import aiorun
import click

from llmailbot.config import FetchConfig, ReplyConfig, SendConfig
from llmailbot.core import AppComponent, run_app
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
        FetchConfig.model_config["yaml_file"] = config_file
        ReplyConfig.model_config["yaml_file"] = config_file
        SendConfig.model_config["yaml_file"] = config_file


def indent(txt, indent_str="  ") -> str:
    return "\n".join(f"{indent_str}{line}" for line in txt.split("\n"))


@cli.command()
@click.argument("components", type=AppComponent, nargs=-1)
@handle_cli_exceptions
def config(components: list[AppComponent]):
    """
    Print loaded configuration in YAML format.
    """
    if not components:
        components = list(AppComponent)

    if AppComponent.FETCH in components:
        fetch_conf = FetchConfig()
        click.echo("Fetch configuration:")
        click.echo(indent(fetch_conf.dump_yaml()))

    if AppComponent.REPLY in components:
        reply_conf = ReplyConfig()
        click.echo("Reply configuration:")
        click.echo(indent(reply_conf.dump_yaml()))

    if AppComponent.SEND in components:
        send_conf = SendConfig()
        click.echo("Send configuration:")
        click.echo(indent(send_conf.dump_yaml()))


@cli.command()
@click.argument("components", type=AppComponent, nargs=-1)
@handle_cli_exceptions
def run(components: list[AppComponent]):
    """
    Start the mail bot.

    By default, runs all components (fetch, reply, send).

    Specify components to run only those.
    """
    aiorun.run(run_app(components=components), stop_on_unhandled_errors=True)


if __name__ == "__main__":
    cli()
