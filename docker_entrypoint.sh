#!/bin/bash

set -euxo pipefail

if [ -f /app/requirements.txt ]; then
  /app/venv/bin/pip install -r /app/requirements.txt
fi

cd /app
exec /app/venv/bin/llmailbot "$@"
