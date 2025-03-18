# LLMailBot

[![CI](https://github.com/jbchouinard/llmailbot/actions/workflows/ci.yml/badge.svg)](https://github.com/jbchouinard/llmailbot/actions/workflows/ci.yml)

LLMailBot enables chatting with LLMs via email. It connects to an email account
using IMAP/SMTP, then automatically responds to incoming emails using LLM chat models.

**If OnFetch=Delete, LLMailBot may delete all the emails in the connected account.**

Any [langchain-supported provider](https://python.langchain.com/docs/integrations/providers/)
should work. You will need to install the relevant langchain Python package and
set them up; provider API keys must be set in environment variables.
Such as `OPENAI_API_KEY` for OpenAI, `ANTHROPIC_API_KEY` for Anthropic, etc.

## Security

**Since generally anyone can email anyone, using LLMailBot means you risk letting**
**unauthorized people indirectly use your LLM API keys or access your self-hosted LLM.**

LLMailBot has basic address filtering, but it's not super secure.
The bot will only reply to emails from addresses in the AllowFrom list.
But AllowFrom only checks the From header on the emails, which is vulnerable to spoofing.

### Email spoofing

Email spoofing is possible because email From headers are just something the sender
writes, they don't need to match where the email actually comes from.

Mail servers use technologies like [SPF, DKIM, and DMARC](https://www.fastmail.com/blog/spf-dkim-dmarc/)
to block malicious spoofed emails, but it's not perfect.
Email spoofing tends to work due to misconfigured mail servers or domains.
So if you only allow addresses from major email providers you should be relatively safe.

To be even more safe, you may want to only allow emails from the same domain as the bot.
For example, if the bot is set up on mybot@example.com, only allow myname@example.com,
myfriend@example.com, etc. It *should* be hard to trick a mail server
into accepting spoofed emails claiming to be from its own domain.

It's much more likely that example.com could be tricked into accepting spoofed emails
from sketchy domains or the domains of small businesses with misconfigured domains/servers.

### Recommendations

I developed LLMailBot for my own personal use. Use it at your own risk. I'd recommend at a minimum:
- **Never connect LLMailBot to a personal email account** - it may delete your emails
- Ideally, use a dedicated, brand new email account
- Only allow specific addresses from domains you trust in AllowFrom
- Use LLM API keys that have rate or cost limits you're comfortable with
- Don't send sensitive information via email
- Don't put sensitive information in system prompts

## Limitations

LLMailBot is not a spam bot. It only responds when receiving an email, and
only responds to the From address. It ignores Reply-To.

Currently only plain text emails are supported. But for accessibility reasons,
well-behaved email clients **should** automatically include a text/plain alternative
version when sending richly formatted emails.

LLMailBot does not store emails or track conversations.
**Usually**, when replying, email clients copy the entire email chain in
the reply. LLMailBot does the same when it replies.
That way the context of the conversation is saved in the emails themselves.

At the moment, the emails are minimally preprocessed, so the quality of responses
depends on the ability of the model to "understand" a chain of quoted replies.
Messages in an email reply chain are usually ordered from newest to oldest, unlike chat messages.
It seems to work OK with the models I tested, but your mileage may vary.

I might try to implement splitting the quoted replies into individual
messages. For now the entire email, including quoted replies, is given to the model
as a single long user message. Ideally it should be split into individual messages
and assigned the proper roles (user or AI).

## Installation

Requirements:
- Python 3.12+

### Install using pipx:

```bash
# Install the package
pipx install git+https://github.com/jbchouinard/llmailbot.git

# Then inject the langchain packages you need
pipx inject llmailbot langchain-openai langchain-anthropic langchain-ollama
```

See the [LangChain documentation](https://python.langchain.com/docs/integrations/providers/) for a list of available providers.

### Install using poetry for development:

```bash
git clone https://github.com/jbchouinard/llmailbot.git
cd llmailbot
# To add more langchain providers for dev:
poetry add --group langchain langchain-groq langchain-ollama ...
poetry install --with langchain
```

## Usage - command line
```bash
python -m llmailbot --help
```

## Configuration

**If OnFetch=Delete in the config, LLMailBot may delete all the emails in the connected account.**

Configuration options are documented in config.example.yaml.

To get started quickly, copy and edit the example config:

```bash
copy config.example.yaml config.yaml
```

### Configuration sources (in order of precedence)

llmailbot loads configuration from multiple sources:

1. **Constructor Arguments**: Values passed directly to the `LLMailBotConfig` constructor
2. **YAML File**: Loaded from one of several possible locations
3. **Secret Files**: Loaded from `/run/secrets` and `/var/run/secrets/llmailbot/`

### YAML configuration file locations

If the config file location is not specified by the --config CLI options,
the app searches for a YAML configuration file in the following locations (in order):

1. `./config.yaml` (current directory)
2. `~/.config/llmailbot/config.yaml` (Unix convention)
3. OS-specific conventional location (using the `config-path` package):
   - **Windows**: Uses `%APPDATA%\net.pigeonland.llmailbot.yaml` (typically `C:\Users\<username>\AppData\Roaming\net.pigeonland.llmailbot.yaml`)
   - **macOS**: `~/Library/Preferences/net.pigeonland.llmailbot.yaml`
   - **Linux/Other**: `~/.config/net.pigeonland.llmailbot.yaml` (follows XDG Base Directory Specification)

### Secret files

Configuration can be loaded from secrets files (e.g. produced by Docker Secrets).

Secret files are loaded from `/run/secrets` or `/var/run/secrets/llmailbot/`. They must be in JSON format.

Each top-level in the YAML config corresponds to a secret file, for example in `/run/secrets`:

| Configuration Section       | Secret File Path                           |
|-----------------------------|--------------------------------------------|
| Models                      | `/run/secrets/models`                      |
| SMTP                        | `/run/secrets/smtp`                        |
| IMAP                        | `/run/secrets/imap`                        |
| Security                    | `/run/secrets/security`                    |
| WorkerPool                  | `/run/secrets/workerpool`                  |
| Queues                      | `/run/secrets/queues`                      |
| ChatModelConfigurableFields | `/run/secrets/chatmodelconfigurablefields` |


## Development

### CI/CD

This project uses GitHub Actions for continuous integration. The following checks run automatically on push and pull requests:

- Linting with ruff
- Code formatting with ruff format
- Unit tests with pytest

### Apply linting and formatting fixes locally:

```bash
poetry run ruff check --fix; poetry run ruff format
```

### Run tests locally:

```bash
poetry run pytest tests
```

## License

TBD

Copyright 2025 Jerome Boisvert-Chouinard
