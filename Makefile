VERSION := $(shell poetry version -s)
DOCKER_REPO ?= "jbchouinard/llmailbot"

all: build docker-build

build:
	poetry build

test:
	poetry run pytest -v tests

lint:
	poetry run ruff check --fix
	poetry run ruff format

docker-build: docker-build-slim docker-build-all

docker-build-all:
	docker build --build-arg "poetry_export_args=--with langchain" -t ${DOCKER_REPO}:all-${VERSION} .
	docker tag ${DOCKER_REPO}:all-${VERSION} ${DOCKER_REPO}:all

docker-build-slim:
	docker build -t ${DOCKER_REPO}:slim-${VERSION} -f Dockerfile .
	docker tag ${DOCKER_REPO}:slim-${VERSION} ${DOCKER_REPO}:slim

clean:
	rm -rf dist/

.PHONY: build lint test clean docker-build docker-build-all docker-build-slim
