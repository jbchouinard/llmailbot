# LLMailBot

LLMailBot is a server app that enables chatting with LLMs via email.

It connects to an email account using IMAP/SMTP, then responds
automatically to incoming emails using langchain chat models.

Any [langchain-supported provider](https://python.langchain.com/docs/integrations/providers/)
should work. You will need to install the relevant langchain Python package and
do the appropriate setup for it, such as providing API keys in env vars.

## Security & Cost Considerations

Since generally anyone can email anyone, using LLMailBot means you risk
letting anyone use your LLM API keys or access your self-hosted LLM.

LLMailBot has rudimentary rate limiting and address filtering,
but it has no protection against address spoofing.
The address filter will prevent random spam from running up your
LLM bill, but not a dedicated attacker.

As a reminder, email is not a secure medium, they are generally sent in
clear text over the internet.

Use at your own risk; I would recommend at least:
- Never connect LLMailBot to a personal email account
- Ideally, use a dedicated, brand new email account
- Don't advertise or sign up to anything with the bot's email address
- Use LLM API keys that have rate or cost limits you're comfortable burning through
- Don't send sensitive information via email

## Limitations

Currently only plaintext emails are supported. But for accessibility reasons,
well-behaved email clients **should** automatically include a plaintext version,
even if you compose a fancy email with HTML formatting.

LLMailBot does not store emails. It does not remember previous emails.
However, **usually**, when replying, email clients copy the entire conversation into the reply.
Otherwise when you forward or add new people to a conversation they would not get
the context. So with emails the context of the conversation is tracked for "free".

At the moment, the emails are not preprocessed in any way, so the quality of the response
depends on the ability of the model to "understand" a chain of quoted replies, which are usually
ordered from newest to oldest, unlike chat messages.

I might try to add some pre-processing to split the reply chain into individual
messages. For now the entire email, including quoted replies, is given to the model
as one big user message. Ideally it should be split into individual messages and correctly
assigned the proper roles (user or machine).


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

### Install with poetry:

```bash
git clone https://github.com/jbchouinard/llmailbot.git
cd llmailbot
poetry install
poetry add langchain-openai langchain-anthropic ...
```

## Usage
```bash
python -m llmailbot --help
```

## Configuration

llmailbot loads configuration from multiple sources:

### Configuration Sources (in order of precedence)

1. **Constructor Arguments**: Values passed directly to the `AppConfig` constructor
2. **Environment Variables**: Prefixed with `LLMAILBOT_` (e.g., `LLMAILBOT_STORAGE__TYPE`, `LLMAILBOT_MAILBOTS__0__NAME`)
3. **Dotenv File**: Variables loaded from `.env` file
4. **YAML Configuration**: Loaded from one of several possible locations
5. **Secret Files**: Loaded from `/run/secrets` and `/var/run/secrets/llmailbot/`

### YAML Configuration File Locations

The application searches for a YAML configuration file in the following locations (in order):

1. `./config.yaml` (current directory)
2. `~/.config/llmailbot/config.yaml` (Unix convention)
3. OS-specific conventional location (using the `config-path` package):
   - **Windows**: Uses `%APPDATA%\net.pigeonland.llmailbot.yaml` (typically `C:\Users\<username>\AppData\Roaming\net.pigeonland.llmailbot.yaml`)
   - **macOS**: `~/Library/Preferences/net.pigeonland.llmailbot.yaml`
   - **Linux/Other**: `~/.config/net.pigeonland.llmailbot.yaml` (follows XDG Base Directory Specification)

### Configuration Example

A sample configuration file is provided at `config.example.yaml`. Copy this file to one of the locations above to get started:

```bash
cp config.example.yaml config.yaml
```

### Environment Variables

API keys for LLM providers must be set as environment variables for the configured models, e.g. `OPENAI_API_KEY`.

All configuration options can also be set using environment variables. Use double underscores (`__`) to represent nested structures
and numeric indices for lists. Environment variables are prefixed with `LLMAILBOT_` and are case-insensitive:

```bash
# Set the name and address of the first mailbot
export LLMAILBOT_MAILBOTS__0__NAME="My Environment Variable Bot"
export LLMAILBOT_MAILBOTS__0__ADDRESS="mybot@example.com"

# Set the model and provider for the first mailbot
export LLMAILBOT_MAILBOTS__0__MODEL="gpt-4.5-preview"
export LLMAILBOT_MAILBOTS__0__MODELPROVIDER="openai"

# Set the SMTP server for mail sending
export LLMAILBOT_MAILSEND__SMTP__SERVER="smtp.gmail.com"

# Set the security filter mode
export LLMAILBOT_SECURITY__FILTERFROM__MODE="AllowList"
```

Complex values can be set in JSON format:

```bash
export LLMAILBOT_SECURITY__FILTERFROM__ADDRESSES='["myname@example.com", "*@mydomain.net"]'
```

### Secret Files

Secret files are loaded from `/run/secrets` and `/var/run/secrets/llmailbot/` and can be used for
sensitive information such as email credentials. They must be in JSON format.

For example, if using `/run/secrets`, the files would be:
- `/run/secrets/mailbots`
- `/run/secrets/mailfetch`
- `/run/secrets/mailsend`
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
