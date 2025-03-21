# pyright: reportCallIssue=false
import sys

import aiorun
import click

from llmailbot.config import FetchConfig, ReplyConfig, SendConfig
from llmailbot.core import AppComponent, run_app
from llmailbot.logging import LogLevel, setup_logging


@click.group()
@click.option("--config", "config_file", default=None, help="Configuration file (default: None)")
@click.option("--log-level", type=str, default=LogLevel.INFO, help="Log level (default: INFO)")
@click.option("--log-file", default=None, help="Log file (default: stderr)")
def cli(config_file: str | None, log_level: str, log_file: str | None):
    setup_logging(log_file, log_level)
    if config_file:
        FetchConfig.model_config["yaml_file"] = config_file
        ReplyConfig.model_config["yaml_file"] = config_file
        SendConfig.model_config["yaml_file"] = config_file


def indent(txt, indent_str="  ") -> str:
    return "\n".join(f"{indent_str}{line}" for line in txt.split("\n"))


@cli.group()
def config():
    pass


@config.command()
@click.argument("components", type=AppComponent, nargs=-1)
def show(components: list[AppComponent]):
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


@config.command()
def example():
    """
    Write example configuration to ./config.yaml.
    """
    import importlib.resources
    from pathlib import Path

    # Check if config.yaml already exists
    config_path = Path("./config.yaml")
    if config_path.exists():
        click.echo(f"Error: {config_path.absolute()} already exists. Will not overwrite.", err=True)
        return

    # Get the example config from package resources
    example_config = (
        importlib.resources.files("llmailbot").joinpath("../examples/config.yaml").read_text()
    )

    # Write to config.yaml
    with open(config_path, "w") as f:
        f.write(example_config)

    click.echo(f"Example configuration written to {config_path.absolute()}")


@config.command()
def interactive():
    """
    Interactively generate a config based on a series of prompts
    and write it to ./config.yaml.
    """
    from pathlib import Path

    import yaml

    # Check if config.yaml already exists
    config_path = Path("./config.yaml")
    if config_path.exists():
        click.echo(f"Error: {config_path.absolute()} already exists. Will not overwrite.", err=True)
        return

    # Initialize the config dictionary
    config = {}

    # IMAP Configuration
    click.echo("\nIMAP Configuration:")
    click.echo("=================\n")
    click.echo("⚠️  WARNING: Use a dedicated email account for LLMailBot. ⚠️")
    click.echo("⚠️  The bot may delete emails from this account. ⚠️\n")

    imap_config = {}
    imap_config["Server"] = click.prompt("IMAP Server", type=str)
    imap_config["Port"] = click.prompt("IMAP Port", type=int, default=993)
    imap_config["Username"] = click.prompt("IMAP Username", type=str)
    imap_password = click.prompt("IMAP Password", hide_input=True, confirmation_prompt=True)
    imap_config["Password"] = imap_password

    # Email fetch configuration
    imap_config["WatchFolder"] = click.prompt(
        "Folder to watch for incoming emails", default="INBOX"
    )
    imap_config["RepliedFolder"] = click.prompt(
        "Move replies to folder", default="LLMailBot/Processed"
    )
    imap_config["BlockedFolder"] = click.prompt(
        "Folder for blocked emails", default="LLMailBot/Blocked"
    )

    # SMTP Configuration
    click.echo("\nSMTP Configuration:")
    click.echo("=================\n")
    click.echo("This is used to send replies to emails.\n")

    smtp_config = {}
    # Try to suggest an SMTP server based on the IMAP server
    suggested_smtp = None
    if imap_config["Server"].startswith("imap."):
        # If IMAP server is imap.example.com, suggest smtp.example.com
        domain = imap_config["Server"][5:]  # Remove "imap."
        suggested_smtp = f"smtp.{domain}"
    smtp_config["Server"] = click.prompt("SMTP Server", type=str, default=suggested_smtp)
    smtp_config["Port"] = click.prompt("SMTP Port", type=int, default=587)
    smtp_config["Username"] = click.prompt(
        "SMTP Username", type=str, default=imap_config["Username"]
    )
    use_same_password = click.confirm("Use same password as IMAP?", default=True)
    if use_same_password:
        smtp_config["Password"] = imap_password
    else:
        smtp_config["Password"] = click.prompt(
            "SMTP Password", hide_input=True, confirmation_prompt=True
        )

    # Model Configuration
    click.echo("\nLLM Configuration:")
    click.echo("================\n")
    click.echo("This configures which LLM to use for generating replies.\n")

    # Create Models list
    models = []
    model_spec = {}

    # Get bot email address
    bot_email = click.prompt("Bot's email address", type=str, default=imap_config["Username"])
    model_spec["Address"] = bot_email

    # Set a name for the model
    model_spec["Name"] = click.prompt("Bot name", default="LLMailBot")

    # Set max input length
    model_spec["MaxInputLength"] = click.prompt("Maximum input length", default=10000, type=int)

    # Configure the chat model
    chat_model_config = {}
    model_provider = click.prompt(
        "Model Provider",
        type=click.Choice(["openai", "anthropic", "google", "ollama", "other"]),
        default="openai",
    )

    if model_provider == "openai":
        chat_model_config["ModelProvider"] = "openai"
        chat_model_config["Model"] = click.prompt("Model Name", default="gpt-4o")
        click.echo("\nPlease set your API key as an environment variable:")
        click.echo("export OPENAI_API_KEY=your_api_key_here")
        click.echo("\nThe API key will be loaded from the environment variable.")
    elif model_provider == "anthropic":
        chat_model_config["ModelProvider"] = "anthropic"
        chat_model_config["Model"] = click.prompt("Model Name", default="claude-3-5-sonnet-latest")
        click.echo("\nPlease set your API key as an environment variable:")
        click.echo("export ANTHROPIC_API_KEY=your_api_key_here")
        click.echo("\nThe API key will be loaded from the environment variable.")
    elif model_provider == "google":
        chat_model_config["ModelProvider"] = "google"
        chat_model_config["Model"] = click.prompt("Model Name", default="gemini-1.5-pro")
        click.echo("\nPlease set your API key as an environment variable:")
        click.echo("export GOOGLE_API_KEY=your_api_key_here")
        click.echo("\nThe API key will be loaded from the environment variable.")
    elif model_provider == "ollama":
        chat_model_config["ModelProvider"] = "ollama"
        chat_model_config["Model"] = click.prompt("Model Name", default="llama3")
        chat_model_config["BaseUrl"] = click.prompt(
            "Ollama Base URL", default="http://localhost:11434"
        )
    else:  # other
        provider_name = click.prompt("Provider Name", type=str)
        chat_model_config["ModelProvider"] = provider_name
        chat_model_config["Model"] = click.prompt("Model Name", type=str)
        if click.confirm("Does this provider require a custom base URL?", default=False):
            chat_model_config["BaseUrl"] = click.prompt("Base URL", type=str)

    # Set other model parameters
    chat_model_config["MaxTokens"] = click.prompt("Maximum tokens", default=2048, type=int)
    chat_model_config["Temperature"] = click.prompt("Temperature", default=0.2, type=float)

    # Add chat model config to model spec
    model_spec["ChatModelConfig"] = chat_model_config

    # Add model spec to models list
    models.append(model_spec)

    # Security Configuration
    click.echo("\nSecurity Configuration:")
    click.echo("=====================\n")
    click.echo("This configures which email addresses are allowed to use the bot.\n")

    security_config = {}
    security_config["AllowFrom"] = []
    user_email = click.prompt("Email address allowed to use the bot", type=str)
    security_config["AllowFrom"].append(user_email)

    while click.confirm("Add another allowed email address?", default=False):
        email = click.prompt("Email address", type=str)
        security_config["AllowFrom"].append(email)

    # Assemble the final config
    config["IMAP"] = imap_config
    config["SMTP"] = smtp_config
    config["Models"] = models
    config["Security"] = security_config

    # Add ChatModelConfigurableFields
    config["ChatModelConfigurableFields"] = [
        "Model",
        "ModelProvider",
        "MaxTokens",
        "Temperature",
        "BaseUrl",
    ]

    # Write to config.yaml
    with open(config_path, "w") as f:
        yaml.dump(config, f, default_flow_style=False, sort_keys=False)

    click.echo(f"\nConfiguration written to {config_path.absolute()}")
    click.echo("You can now run LLMailBot with: llmailbot run")


@cli.command()
@click.argument("components", type=AppComponent, nargs=-1)
@click.option("--threads", type=int, default=2, help="Number of threads to use (default: 2)")
def run(components: list[AppComponent], threads: int):
    """
    Start the mail bot.

    By default, runs all components (fetch, reply, send).

    Specify components to run only those.
    """

    aiorun.run(
        run_app(components=components),
        stop_on_unhandled_errors=True,
        timeout_task_shutdown=10,
        executor_workers=threads,
    )


def main():
    try:
        cli(auto_envvar_prefix="LLMAILBOT")
    except Exception as e:
        click.echo(f"Error: {str(e)}", err=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
