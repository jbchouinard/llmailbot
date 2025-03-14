import click
from loguru import logger


@click.command()
def main():
    logger.info("Hello World from Loguru!")
    click.echo("Hello World from Click!")


if __name__ == "__main__":
    main()
