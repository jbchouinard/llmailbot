FROM thehale/python-poetry:2.1.1-py3.12-slim AS build

WORKDIR /app

COPY pyproject.toml poetry.lock /app/
COPY README.md /app/
COPY llmailbot /app/llmailbot
# must run install at least once to ensure poetry plugins are installed
# it works even with --dry-run
RUN poetry install --dry-run
RUN poetry build -f wheel
# Export requirements
RUN poetry export --without-hashes -E redis --format=requirements.txt --without dev > dist/requirements.txt

FROM python:3.12-slim AS runtime

WORKDIR /app

RUN python -m venv /app/venv

COPY --from=build /app/dist /app/dist

RUN /app/venv/bin/pip install --upgrade pip && \
    /app/venv/bin/pip install -r /app/dist/requirements.txt && \
    /app/venv/bin/pip install /app/dist/*.whl && \
    rm -rf /root/.cache/pip

COPY docker_entrypoint.sh /app/docker_entrypoint.sh

ENTRYPOINT ["/app/docker_entrypoint.sh"]
CMD ["run"]
