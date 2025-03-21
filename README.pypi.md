# LLMailBot

LLMailBot is a service that enables chatting with Large Language Models (LLMs) via email. It connects to an email account using IMAP/SMTP protocols, then automatically responds to incoming emails using LLM chat models like GPT-4, Claude, or other compatible models.

**⚠️ IMPORTANT: LLMailBot may delete emails in the connected account. Always use a dedicated email account created specifically for this purpose, never your personal email account.**

## Key Features

- **LLM Integration**: Uses LangChain chat models to provide compatibility with most mainstream LLMs
- **Security**: Includes basic security features such as rate limiting and address filtering
- **Dynamic Configuration**: Supports multiple model configurations based on pattern-matching email addresses
- **Scalability**: Horizontally scalable architecture using Redis queues for high-volume deployments
- **Flexible Deployment**: Run using Pipx, Docker, or Docker Compose depending on your needs

## Documentation

For complete documentation, installation instructions, and security considerations, please visit the [GitHub repository](https://github.com/jbchouinard/llmailbot).

## Installation

```bash
# Install the base package
pipx install llmailbot

# Add LangChain provider packages for your preferred LLMs
pipx inject llmailbot langchain-openai langchain-anthropic langchain-ollama
```

## Security Warning

**⚠️ WARNING: Since generally anyone can email anyone, using LLMailBot means you risk letting unauthorized people indirectly use your LLM API keys or access your self-hosted LLM.**

For security recommendations and detailed configuration options, please refer to the [full documentation](https://github.com/jbchouinard/llmailbot#security-considerations).
