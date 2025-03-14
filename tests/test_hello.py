from click.testing import CliRunner

from jbmailbot.__main__ import main


def test_hello_world():
    runner = CliRunner()
    result = runner.invoke(main)
    assert result.exit_code == 0
