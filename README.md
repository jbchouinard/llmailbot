# LLMailBot

[![CI](https://github.com/jbchouinard/llmailbot/actions/workflows/ci.yml/badge.svg)](https://github.com/jbchouinard/llmailbot/actions/workflows/ci.yml)
[![Docker](https://img.shields.io/docker/v/jbchouinard/llmailbot?logo=docker&label=Docker%20Hub)](https://hub.docker.com/r/jbchouinard/llmailbot)

LLMailBot is a service that enables chatting with LLMs via email. It connects to an email account
using IMAP/SMTP, then automatically responds to incoming emails using LLM chat models.

**LLMailBot may delete emails in the connected account, don't use it with a personal email account.**

Features:
 - uses [langchain chat models](https://python.langchain.com/docs/integrations/chat); compatible with most mainstream LLMs
 - basic security, including rate limiting and address filtering
 - dynamic model configuration based on pattern-matching email addresses
 - horizontally scaleable (using Redis queues)

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
**Usually**, when replying, email clients copy the entire chain in
the reply. LLMailBot does the same when it replies.
That way the context of the conversation is saved in the emails themselves.

At the moment, the emails are minimally preprocessed, so the quality of responses
depends on the ability of the model to "understand" a chain of quoted replies.
Messages in the chain are usually ordered from newest to oldest, unlike chat messages.
It seems to work OK with the models I tested, but your mileage may vary.

## Getting started

### Pipx

Save and edit a copy of [config.example.yaml](./config.example.yaml).

If you place the config in a [standard location](#yaml-configuration-file-locations),
you can omit the `--config` option.

```bash
# Install llmailbot
pipx install git+https://github.com/jbchouinard/llmailbot.git

# Then install the langchain packages you need, for example:
pipx inject llmailbot langchain-openai langchain-anthropic langchain-ollama

# Start the service
llmailbot --config path/to/config.yaml run
```

### Docker

Save and edit a copy of [config.example.yaml](./config.example.yaml).

The docker image is built in two variants, `slim` and `all`.
The `all` variant has most langchain provider packages pre-installed,
and should work out of the box with most models:

```bash
docker run -v /path/to/config.yaml:/app/config.yaml jbchouinard/llmailbot:all
```

The `slim` variant doesn't have any `langchain-*` packages installed.
You must mount a [requirements.txt](./docker-compose/requirements.txt) file to install whatever
provider packages you need, for example:

```
# requirements.txt
langchain-openai
langchain-anthropic
```

```bash
docker run -v /path/to/config.yaml:/app/config.yaml -v /path/to/requirements.txt:/app/requirements.txt jbchouinard/llmailbot:slim
```

### Docker Compose

See [docker-compose.yaml](./docker-compose/docker-compose.yaml), [config.yaml](./docker-compose/config.yaml), and [requirements.txt](./docker-compose/requirements.txt) for a minimal example for
running the service with replication, using Redis queues.

See [config.example.yaml](./config.example.yaml) for more details on all the options.

### Poetry (for development)

```bash
git clone https://github.com/jbchouinard/llmailbot.git
cd llmailbot
# To add more langchain providers for dev:
poetry add --group langchain langchain-groq langchain-ollama
poetry install --with langchain
poetry run llmailbot --help
```

## Configuration

**If OnFetch=Delete in the config, LLMailBot may delete all the emails in the connected account.**

Configuration options are documented in [config.example.yaml](./config.example.yaml).

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

Each top-level block in the YAML config corresponds to a secret file:

| Configuration Section       | Secret File Path                      |
|-----------------------------|---------------------------------------|
| Models                      | `secrets/models`                      |
| ChatModelConfigurableFields | `secrets/chatmodelconfigurablefields` |
| SMTP                        | `secrets/smtp`                        |
| IMAP                        | `secrets/imap`                        |
| Security                    | `secrets/security`                    |
| WorkerPool                  | `secrets/workerpool`                  |
| ReceiveQueue                | `secrets/receivequeue`                |
| SendQueue                   | `secrets/sendqueue`                   |

## Development

### CI/CD

This project uses GitHub Actions for continuous integration and delivery:

- **CI Workflow**: Runs on push to main and pull requests
  - Linting with ruff
  - Code formatting with ruff format
  - Unit tests with pytest
  - Docker build test

- **Docker Publish Workflow**: Runs on push to main, tags with 'v*' pattern, and releases
  - Builds and pushes Docker images to Docker Hub
  - Creates two variants: `slim` (without langchain packages) and `all` (with langchain packages)

### Apply linting and formatting fixes locally:

```bash
poetry run ruff check --fix; poetry run ruff format
```

### Run tests locally:

```bash
poetry run pytest tests
```

## License

This project is licensed under the MIT License - see the [LICENSE](./LICENSE) file for details.

Copyright 2025 Jerome Boisvert-Chouinard
