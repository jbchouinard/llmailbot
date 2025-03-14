# jbmailbot

A simple bot for chatting with LLMs via email.

## Installation

Requirements:
- Python 3.11+

### Install with pipx:

```bash
pipx install git+https://github.com/jbchouinard/jbmailbot.git
```

### Install for development:

```bash
git clone https://github.com/jbchouinard/jbmailbot.git
cd jbmailbot
poetry install
```

## Configuration

jbmailbot loads configuration from multiple sources:

### Configuration Sources (in order of precedence)

1. **Constructor Arguments**: Values passed directly to the `AppConfig` constructor
2. **Environment Variables**: Prefixed with `JBMAILBOT_` (e.g., `JBMAILBOT_STORAGE__TYPE`, `JBMAILBOT_MAILBOTS__0__NAME`)
3. **Dotenv File**: Variables loaded from `.env` file
4. **YAML Configuration**: Loaded from one of several possible locations
5. **Secret Files**: Loaded from `/var/run/secrets/jbmailbot/`

### YAML Configuration File Locations

The application searches for a YAML configuration file in the following locations (in order):

1. `./config.yaml` (current directory)
2. `~/.config/jbmailbot/config.yaml` (Unix convention)
3. OS-specific conventional location (using the `config-path` package):
   - **Windows**: Uses `%APPDATA%\net.pigeonland.jbmailbot.yaml` (typically `C:\Users\<username>\AppData\Roaming\net.pigeonland.jbmailbot.yaml`)
   - **macOS**: `~/Library/Preferences/net.pigeonland.jbmailbot.yaml`
   - **Linux/Other**: `~/.config/net.pigeonland.jbmailbot.yaml` (follows XDG Base Directory Specification)

### Configuration Example

A sample configuration file is provided at `config.example.yaml`. Copy this file to one of the locations above to get started:

```bash
cp config.example.yaml config.yaml
```

### Configuration Structure

```yaml
MailBots:
  - Name: "My LLM Chatbot"
    SMTP:
      Username: chatbot@example.com
      Password: your-password
      Server: smtp.example.com
      Port: 465
      Encryption: ssl/tls  # Options: none, starttls, ssl/tls
    IMAP:
      Username: chatbot@example.com
      Password: your-password
      Server: imap.example.com
      Port: 993
      Encryption: ssl/tls  # Options: none, starttls, ssl/tls

Storage:
  Type: sqlite
  Path: data/jbmailbot.db

Security:
  Mode: allowlist  # Options: none, allowlist, denylist
  Addresses:
    - "me@example.com"
  RateLimit:  # Optional global rate limit
    Limit: 100
    Window: "1 hour"
  RateLimitPerSender:  # Optional per-sender rate limit
    Limit: 10
    Window: "1 hour"
```

### Environment Variables

All configuration options can also be set using environment variables. Use double underscores (`__`) to represent nested structures and numeric indices for lists:

```bash
# Set the name of the first mailbot
export JBMAILBOT_MAILBOTS__0__NAME="My Environment Variable Bot"

# Set the SMTP server for the first mailbot
export JBMAILBOT_MAILBOTS__0__SMTP__SERVER="smtp.gmail.com"

# Set the security mode
export JBMAILBOT_SECURITY__MODE="allowlist"
```

### Secret Files

Secret files are loaded from `/run/secrets` and `/var/run/secrets/jbmailbot/` and can be used for
sensitive information such as email credentials.

The secret files are named `storage`, `mailbots`, and `security`, and should contain
the corresponding configuration in JSON format.

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
