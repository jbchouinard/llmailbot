# LLMailBot

LLMailBot is a server app that enables chatting with LLMs via email.
It automatically responds to incoming emails on the connected account using LLM chat models.

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

LLMailBot does not store emails or conversations.
But, **usually**, when replying, email clients copy the entire email chain in
the reply. LLMailBot does the same when it replies.
So with emails the context of the conversation is usually maintained by default.

At the moment, the emails are not preprocessed in any way, so the quality of the response
depends on the ability of the model to "understand" a chain of quoted replies,
which are usually ordered from newest to oldest, unlike chat messages.

I might try to implement splitting the reply chain into individual
messages. For now the entire email, including quoted replies, is given to the model
as one big user message. Ideally it should be split into individual messages and correctly
assigned the proper roles (user or AI).

## Installation

Requirements:
- Python 3.12+

### Install with pip:

```bash
pip install git+https://github.com/jbchouinard/llmailbot.git
# Must install langchain packages for LLM providers you want to use
# See: https://python.langchain.com/docs/integrations/providers/
pip install langchain-openai langchain-anthropic ...
```

### Install for development with poetry:

```bash
git clone https://github.com/jbchouinard/llmailbot.git
cd llmailbot
poetry install
poetry add langchain-openai langchain-anthropic ...
```

## Usage - command line
```bash
python -m llmailbot --help
```

## Configuration

**If set to OnFetch=Delete, LLMailBot may delete all the emails in the connected account.**

Configuration options are documented in config.example.yaml.

To get started quickly, copy and edit the example config:

```bash
copy config.example.yaml config.yaml
```

### Configuration sources (in order of precedence)

llmailbot loads configuration from multiple sources:

1. **Constructor Arguments**: Values passed directly to the `LLMailBotConfig` constructor
2. **Environment Variables**: Prefixed with `LLMAILBOT_` (e.g., `LLMAILBOT_MODELS__0__NAME`)
3. **Dotenv File**: Variables loaded from `.env` file
4. **YAML Configuration**: Loaded from one of several possible locations
5. **Secret Files**: Loaded from `/run/secrets` and `/var/run/secrets/llmailbot/`

### YAML configuration file locations

The app searches for a YAML configuration file in the following locations (in order):

1. `./config.yaml` (current directory)
2. `~/.config/llmailbot/config.yaml` (Unix convention)
3. OS-specific conventional location (using the `config-path` package):
   - **Windows**: Uses `%APPDATA%\net.pigeonland.llmailbot.yaml` (typically `C:\Users\<username>\AppData\Roaming\net.pigeonland.llmailbot.yaml`)
   - **macOS**: `~/Library/Preferences/net.pigeonland.llmailbot.yaml`
   - **Linux/Other**: `~/.config/net.pigeonland.llmailbot.yaml` (follows XDG Base Directory Specification)

### Environment variables

API keys for LLM providers must be set as environment variables for the configured models, e.g. `OPENAI_API_KEY`.

All configuration options can also be set using environment variables. Use double underscores (`__`) to represent nested structures
and numeric indices for lists. Environment variables are prefixed with `LLMAILBOT_` and are case-insensitive:

```bash
# Set the name and address of the first mailbot
export LLMAILBOT_MODELS__0__NAME="My Environment Variable Bot"
export LLMAILBOT_MODELS__0__ADDRESS="mybot@example.com"
```

Complex values, e.g. lists, can be set in JSON format:

```bash
export LLMAILBOT_SECURITY__ALLOWFROM='["myname@example.com", "*@mydomain.net"]'
```

Nested maps supports either method:

```bash
# Set the SMTP server for mail sending
export LLMAILBOT_SMTP__SERVER="smtp.example.com"
export LLMAILBOT_SMTP__PORT="465"
export LLMAILBOT_SMTP__USERNAME="mybot@example.com"
export LLMAILBOT_SMTP__PASSWORD="my-secret-password"

export LLMAILBOT_SMTP = '{"Server": "...", "Port": 465, "Username": "...", "Password": "..."}'
```

### Secret files

Configuration can be loaded from secrets files (e.g. produced by Docker Secrets).

Secret files are loaded from `/run/secrets` and `/var/run/secrets/llmailbot/`. They must be in JSON format.

Each top-level in the YAML config corresponds to a secret file, so for example:
- `/run/secrets/models`
- `/run/secrets/smtp`
- `/run/secrets/imap`
...

## Development

### Apply linting and formatting fixes:

```bash
poetry run ruff check --fix; poetry run ruff format
```

### Run tests:

```bash
poetry run pytest tests
```

## License

TBD

Copyright 2025 Jerome Boisvert-Chouinard
