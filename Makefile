.PHONY: help build up down restart logs clean dev-setup test

help: ## Show this help message
	@echo 'Usage: make [target]'
	@echo ''
	@echo 'Available targets:'
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'

build: ## Build Docker images
	docker-compose build

up: ## Start services
	docker-compose up -d

down: ## Stop services
	docker-compose down

restart: down up ## Restart services

logs: ## View logs (follow)
	docker-compose logs -f

logs-bot: ## View bot logs only
	docker-compose logs -f bot

logs-db: ## View database logs only
	docker-compose logs -f db

clean: ## Stop services and remove volumes
	docker-compose down -v

dev-setup: ## Setup development environment
	python -m venv venv
	./venv/bin/pip install -r requirements.txt
	cp .env.example .env
	@echo "✅ Development environment ready!"
	@echo "   Edit .env with your configuration"
	@echo "   Activate venv: source venv/bin/activate"

shell: ## Access bot container shell
	docker-compose exec bot /bin/bash

db-shell: ## Access database shell
	docker-compose exec db psql -U gatekeeper gatekeeper

status: ## Show service status
	docker-compose ps

backup-db: ## Backup database
	docker-compose exec db pg_dump -U gatekeeper gatekeeper > backup_$(shell date +%Y%m%d_%H%M%S).sql
	@echo "✅ Database backed up"

restore-db: ## Restore database (use: make restore-db FILE=backup.sql)
	@test -n "$(FILE)" || (echo "Error: FILE not specified. Usage: make restore-db FILE=backup.sql" && exit 1)
	cat $(FILE) | docker-compose exec -T db psql -U gatekeeper gatekeeper
	@echo "✅ Database restored from $(FILE)"

init-db: ## Initialize database tables
	docker-compose exec bot python -c "import asyncio; from bot.db.database import init_database; from bot.util.config_loader import load_config; asyncio.run(init_database(load_config().database_url))"
	@echo "✅ Database initialized"