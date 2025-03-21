# LLMailBot

[![CI](https://github.com/jbchouinard/llmailbot/actions/workflows/ci.yml/badge.svg)](https://github.com/jbchouinard/llmailbot/actions/workflows/ci.yml)
[![Docker](https://img.shields.io/docker/v/jbchouinard/llmailbot?logo=docker&label=Docker%20Hub)](https://hub.docker.com/r/jbchouinard/llmailbot)
[![PyPI](https://img.shields.io/pypi/v/llmailbot?logo=python&logoColor=white)](https://pypi.org/project/llmailbot/)

LLMailBot is a service that enables chatting with Large Language Models (LLMs) via email. It connects to an email account using IMAP/SMTP protocols, then automatically responds to incoming emails using LLM chat models like GPT-4, Claude, or other compatible models.

**⚠️ IMPORTANT: LLMailBot may delete emails in the connected account. Always use a dedicated email account created specifically for this purpose, never your personal email account.**

Note that sending programatically generated emails to third parties may be against the terms of service of your email provider.

## Key Features

- **LLM Integration**: Uses [LangChain chat models](https://python.langchain.com/docs/integrations/chat) to provide compatibility with most mainstream LLMs
- **Security**: Includes basic security features such as rate limiting and address filtering
- **Dynamic Configuration**: Supports multiple model configurations based on pattern-matching email addresses
- **Scalability**: Horizontally scalable architecture using Redis queues for high-volume deployments
- **Flexible Deployment**: Run using Pipx, Docker, or Docker Compose depending on your needs

## Security Considerations

**⚠️ WARNING: Since generally anyone can email anyone, using LLMailBot means you risk letting unauthorized people indirectly use your LLM API keys or access your self-hosted LLM.**

LLMailBot has basic address filtering, but it is not extremely secure:
- LLMailBot will only reply to emails from addresses in the `AllowFrom` list configured in your settings.
- However, the `AllowFrom` filter only checks the From header of incoming emails, which is vulnerable to spoofing.

### Email Spoofing

Email spoofing is possible because email From headers are just something the sender
writes, they don't need to match where the email actually comes from.

Mail servers use technologies like [SPF, DKIM, and DMARC](https://www.fastmail.com/blog/spf-dkim-dmarc/)
to block malicious spoofed emails, but it's not perfect.
Email spoofing tends to work due to misconfigured mail servers or domains.
So if you only allow addresses from major email providers you should be relatively safe.

To be even more safe, you may want to only allow emails from the same domain as the service.
For example, if LLMailBot is set up on myservice@example.com, only allow myname@example.com,
myfriend@example.com, etc. It *should* be hard to trick a mail server
into accepting spoofed emails claiming to be from its own domain.

It's much more likely that example.com could be tricked into accepting spoofed emails
from sketchy domains or the domains of small businesses with misconfigured domains/servers.

### Security Recommendations

I developed LLMailBot for my own personal use. Use it at your own risk.

- **Never connect LLMailBot to a personal email account** - it may delete your emails
- **Create a dedicated email account** specifically for LLMailBot usage
- **Configure restrictive AllowFrom settings** - only allow specific addresses from domains you trust
- **Set up API key limitations** - use LLM API keys with rate or cost limits you're comfortable with
- **Avoid sensitive information** - don't send sensitive data via email or include it in system prompts

## Limitations

Only plain text emails are supported. But for accessibility reasons,
well-behaved email clients **should** automatically include a text/plain alternative
version when sending richly formatted emails.

LLMailBot does not store emails or track conversations.
**Usually**, when replying, email clients copy the entire chain in
the reply. LLMailBot does the same when it replies.
That way the context of the conversation is saved in the emails themselves.

Emails are minimally preprocessed, so the quality of responses
depends on the ability of models to "understand" nested quoted replies.
Messages in the chain are usually ordered from newest to oldest, unlike chat messages.
It seems to work OK with the models I tested, but your mileage may vary.

## Getting started

### Installation with Pipx

1. **Install LLMailBot**:
   ```bash
   # Install from PyPI (recommended)
   pipx install llmailbot
   
   # Or install directly from GitHub
   pipx install git+https://github.com/jbchouinard/llmailbot.git
   ```

2. **Add LangChain provider packages** for your preferred LLMs:
   ```bash
   # Install only the providers you need
   pipx inject llmailbot langchain-openai langchain-anthropic langchain-ollama
   ```

3. **Create your configuration**:
   ```bash
   # Interactive configuration
   llmailbot config interactive
   
   # Or generate an example configuration and edit it manually
   llmailbot config example
   # Then edit the generated config.yaml file
   ```
   
   If you place the config in a [standard location](#yaml-configuration-file-locations), you can omit the `--config` option.

4. **Start the service**:
   ```bash
   # Run with your configuration file
   llmailbot --config path/to/config.yaml run
   ```

### Deployment with Docker

1. **Prepare your configuration**:
   - Use the interactive configuration command to create your config file:
     ```bash
     llmailbot config interactive
     ```
   - Or copy and edit the example configuration:
     ```bash
     llmailbot config example
     # Then edit the generated config.yaml file
     ```

2. **Choose a Docker image variant**:

   #### Option A: `all` variant (larger but more convenient)
   
   The `all` variant includes these langchain provider packages pre-installed:
   - langchain-ai21 - AI21 models (Jurassic)
   - langchain-anthropic - Anthropic models (Claude)
   - langchain-aws - AWS Bedrock models
   - langchain-azure-ai - Azure OpenAI models
   - langchain-cohere - Cohere models
   - langchain-fireworks - Fireworks AI models
   - langchain-google-genai - Google Gemini models
   - langchain-google-vertexai - Google Vertex AI models
   - langchain-groq - Groq models (LLaMA, Mixtral)
   - langchain-mistralai - Mistral AI models
   - langchain-nvidia-ai-endpoints - NVIDIA AI models
   - langchain-openai - OpenAI models (GPT-3.5, GPT-4, etc.)
   - langchain-together - Together AI models
   - langchain-xai - XAI models

   Run the `all` variant (works out of the box with most popular models):
   ```bash
   docker run -d --name llmailbot \
     -v /absolute/path/to/config.yaml:/app/config.yaml \
     jbchouinard/llmailbot:all
   ```

   #### Option B: `slim` variant (smaller but requires extra setup)
   
   The `slim` variant has no langchain provider packages pre-installed, making it smaller but requiring additional setup:

   1. Create a `requirements.txt` file with your needed providers, e.g.:
      ```
      # requirements.txt
      langchain-openai
      langchain-anthropic
      ```

   2. Run the `slim` variant with your requirements:
      ```bash
      docker run -d --name llmailbot \
        -v /absolute/path/to/config.yaml:/app/config.yaml \
        -v /absolute/path/to/requirements.txt:/app/requirements.txt \
        jbchouinard/llmailbot:slim
      ```

### Deployment with Docker Compose

The repo has example files for deploying with Docker Compose in the [docker-compose](./docker-compose) directory.

1. **Example files**:
   - [docker-compose.yaml](./docker-compose/docker-compose.yaml) - Service configuration with Redis for queuing
   - [config.yaml](./docker-compose/config.yaml) - Example configuration for Docker Compose setup
   - [requirements.txt](./docker-compose/requirements.txt) - Example requirements for the slim variant

2. **Start the services**:
   ```bash
   cd docker-compose
   docker-compose up -d
   ```

3. **Scale services horizontally** (optional):
   ```bash
   # Run 3 worker instances for parallel processing
   docker-compose up -d --scale worker=3
   
   # You can scale any service as needed
   docker-compose up -d --scale fetcher=2 --scale worker=5 --scale sender=2
   ```

   The `--scale` option creates multiple instances of a service, enabling:
   - Increased throughput by processing more emails in parallel
   - Better resource utilization across multiple CPU cores
   - Improved reliability through redundancy

See [examples/config.yaml](./examples/config.yaml) for detailed configuration options and explanations.

### Development Setup with Poetry

1. **Clone the repository**:
   ```bash
   git clone https://github.com/jbchouinard/llmailbot.git
   cd llmailbot
   ```

2. **Install dependencies**:
   ```bash
   # Install base dependencies
   poetry install
   
   # (Optional) Add additional langchain providers
   poetry add --group langchain langchain-ollama
   
   # Install with langchain group
   poetry install --with langchain
   ```

3. **Run the application**:
   ```bash
   # View available commands
   poetry run llmailbot --help
   
   # Run with a config file
   poetry run llmailbot --config path/to/config.yaml run
   ```

## Configuration Options

**⚠️ WARNING: If `RepliedFolder` or `BlockedFolder` are set to null, LLMailBot will delete emails instead of moving them.**

All configuration options are documented in [examples/config.yaml](./examples/config.yaml) with explanations and examples.

### Configuration Sources (in order of precedence)

llmailbot loads configuration from multiple sources:

1. **Constructor Arguments**: Values passed directly to the `LLMailBotConfig` constructor
2. **YAML File**: Loaded from one of several possible locations
3. **Secret Files**: Loaded from `/run/secrets` and `/var/run/llmailbot/secrets/`

### YAML Configuration File Locations

If the config file location is not specified by the --config CLI options,
the app searches for a YAML configuration file in the following locations (in order):

1. `./config.yaml` (current directory)
2. `~/.config/llmailbot/config.yaml` (Unix convention)
3. OS-specific conventional location (using the `config-path` package):
   - **Windows**: Uses `%APPDATA%\net.pigeonland.llmailbot.yaml` (typically `C:\Users\<username>\AppData\Roaming\net.pigeonland.llmailbot.yaml`)
   - **macOS**: `~/Library/Preferences/net.pigeonland.llmailbot.yaml`
   - **Linux/Other**: `~/.config/net.pigeonland.llmailbot.yaml` (follows XDG Base Directory Specification)

### Secret Files

#### Configuration

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
| ReceiveQueue                | `secrets/receivequeue`                |
| SendQueue                   | `secrets/sendqueue`                   |

#### API Keys

LLMailBot supports loading provider API keys from files by setting `PROVIDER_API_KEY_FILE` environment variables.
For example, to load OpenAI API keys from a Docker secret, you could set set:

```yaml
services:
  llmailbot:
    ...
    secrets:
      - source: openai_api_key
        target: /run/secrets/openai_api_key
    environment:
      ...
      - OPENAI_API_KEY_FILE=/run/secrets/openai_api_key
```

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

### Development Workflow

#### Code Quality

Apply linting and formatting fixes locally:
```bash
# Run linting checks and auto-fix issues
poetry run ruff check --fix

# Format code according to project standards
poetry run ruff format
```

#### Testing

Run the test suite locally:
```bash
# Run all tests
poetry run pytest tests

# Run with verbose output
poetry run pytest -v tests

# Run a specific test file
poetry run pytest tests/test_specific_module.py
```

## License

This project is licensed under the MIT License - see the [LICENSE](./LICENSE) file for details.

Copyright 2025 Jerome Boisvert-Chouinard
