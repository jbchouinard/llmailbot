VERSION := $(shell poetry version -s)

all: build docker-build

build:
	poetry build

test:
	poetry run pytest -v tests

lint:
	poetry run ruff check --fix
	poetry run ruff format

docker-build:
	docker build -t llmailbot:slim-${VERSION} -f Dockerfile .
	docker tag llmailbot:slim-${VERSION} llmailbot:slim
	docker build --build-arg "poetry_export_args=--with langchain" -t llmailbot:all-${VERSION} .
	docker tag llmailbot:all-${VERSION} llmailbot:all

clean:
	rm -rf dist/

.PHONY: build docker-build clean lint test
