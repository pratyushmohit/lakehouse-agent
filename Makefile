.PHONY: install build up down dev mcp-server test

install:
	uv sync

build:
	docker compose build

up:
	docker compose up -d

down:
	docker compose down

dev:
	uv run uvicorn src.app:app --reload --port 8000

mcp-server:
	uv run python -m src.mcp_server.server

test:
	make install && uv run pytest
