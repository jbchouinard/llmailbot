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

docker-build-slim: Dockerfile
	DOCKER_BUILDKIT=1 docker buildx build \
		--build-arg BUILDKIT_INLINE_CACHE=1 \
		--build-arg variant=slim \
		-t ${DOCKER_REPO}:slim-${VERSION} -f $< .
	docker tag ${DOCKER_REPO}:slim-${VERSION} ${DOCKER_REPO}:slim

docker-build-all: Dockerfile
	DOCKER_BUILDKIT=1 docker buildx build \
		--build-arg BUILDKIT_INLINE_CACHE=1 \
		--build-arg variant=all \
		-t ${DOCKER_REPO}:all-${VERSION} -f $< .
	docker tag ${DOCKER_REPO}:all-${VERSION} ${DOCKER_REPO}:all

clean:
	rm -rf dist/

.PHONY: build lint test clean docker-build docker-build-all docker-build-slim
