COMPOSE_FILE := deploy/compose/docker-compose.yml
COMPOSE := docker compose --env-file .env -f $(COMPOSE_FILE)

.PHONY: check test compile frontend-build up down build ps logs

check: compile test

compile:
	python -m compileall -q backend scripts

test:
	python -m pytest backend/tests -q

frontend-build:
	npm --prefix frontend run build

up:
	$(COMPOSE) up -d

down:
	$(COMPOSE) down

build:
	$(COMPOSE) build

ps:
	$(COMPOSE) ps

logs:
	$(COMPOSE) logs --tail=100
