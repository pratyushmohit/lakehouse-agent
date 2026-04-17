.PHONY: install build up down

install:
	uv sync

build:
	docker compose build

up:
	docker compose up -d

down:
	docker compose down
