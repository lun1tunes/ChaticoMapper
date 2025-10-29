# Makefile for Chatico Mapper App
# Simplifies common Docker and development tasks

.PHONY: help build up up-logs down down-volumes restart logs logs-app logs-postgres logs-redis shell shell-db shell-redis migrate migrate-rollback migrate-create install test test-cov lint format ps stats health clean clean-all backup-db restore-db monitor monitor-webhooks watch-redis

# Colors for output
RED := \033[0;31m
GREEN := \033[0;32m
YELLOW := \033[1;33m
NC := \033[0m # No Color

help: ## Show this help message
	@echo "$(GREEN)Chatico Mapper App - Available Commands:$(NC)"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  $(YELLOW)%-20s$(NC) %s\n", $$1, $$2}'

# ============================================================================
# Docker Commands
# ============================================================================

build: ## Build Docker images
	@echo "$(GREEN)Building Docker images...$(NC)"
	cd docker && docker-compose build

up: ## Start all services
	@echo "$(GREEN)Starting all services...$(NC)"
	cd docker && docker-compose up -d
	@echo "$(GREEN)Services started! App available at http://localhost:8000$(NC)"
	@echo "$(GREEN)API docs at http://localhost:8000/docs$(NC)"

up-logs: ## Start services and show logs
	@echo "$(GREEN)Starting services with logs...$(NC)"
	cd docker && docker-compose up

down: ## Stop all services
	@echo "$(RED)Stopping all services...$(NC)"
	cd docker && docker-compose down

down-volumes: ## Stop services and remove volumes (WARNING: deletes data!)
	@echo "$(RED)Stopping services and removing volumes...$(NC)"
	cd docker && docker-compose down -v

restart: ## Restart all services
	@echo "$(YELLOW)Restarting services...$(NC)"
	$(MAKE) down
	$(MAKE) up

logs: ## Show logs from all services
	cd docker && docker-compose logs -f

logs-app: ## Show logs from app only
	cd docker && docker-compose logs -f app

logs-postgres: ## Show logs from PostgreSQL
	cd docker && docker-compose logs -f postgres

logs-redis: ## Show logs from Redis
	cd docker && docker-compose logs -f redis

# ============================================================================
# Application Commands
# ============================================================================

shell: ## Open shell in app container
	docker exec -it chatico-mapper-app bash

shell-db: ## Open psql shell
	docker exec -it chatico-mapper-postgres psql -U chatico_user -d chatico_mapper

shell-redis: ## Open redis-cli shell
	docker exec -it chatico-mapper-redis redis-cli -a chatico_password

migrate: ## Run database migrations
	@echo "$(GREEN)Running database migrations...$(NC)"
	docker exec -it chatico-mapper-app sh -c "cd database && alembic upgrade head"

migrate-rollback: ## Rollback last migration
	@echo "$(YELLOW)Rolling back last migration...$(NC)"
	docker exec -it chatico-mapper-app sh -c "cd database && alembic downgrade -1"

migrate-create: ## Create new migration (usage: make migrate-create MESSAGE="description")
	@echo "$(GREEN)Creating new migration...$(NC)"
	docker exec -it chatico-mapper-app sh -c "cd database && alembic revision -m '$(MESSAGE)'"

# ============================================================================
# Development Commands
# ============================================================================

install: ## Install dependencies locally
	poetry install

test: ## Run tests
	poetry run pytest

test-cov: ## Run tests with coverage
	poetry run pytest --cov=src --cov-report=html --cov-report=term

lint: ## Run code linting
	poetry run black src/
	poetry run isort src/
	poetry run flake8 src/

format: ## Format code
	poetry run black src/
	poetry run isort src/

# ============================================================================
# Utility Commands
# ============================================================================

ps: ## Show running containers
	cd docker && docker-compose ps

stats: ## Show container resource usage
	docker stats chatico-mapper-app chatico-mapper-postgres chatico-mapper-redis --no-stream

health: ## Check health of all services
	@echo "$(GREEN)Checking service health...$(NC)"
	@curl -s http://localhost:8000/health | jq '.' || echo "$(RED)App not responding$(NC)"

clean: ## Clean up Docker resources
	@echo "$(YELLOW)Cleaning up Docker resources...$(NC)"
	docker system prune -f

clean-all: ## Clean up all Docker resources including volumes
	@echo "$(RED)WARNING: This will delete all data!$(NC)"
	@read -p "Are you sure? [y/N] " -n 1 -r; \
	echo; \
	if [[ $$REPLY =~ ^[Yy]$$ ]]; then \
		cd docker && docker-compose down -v; \
		docker system prune -af --volumes; \
	fi

backup-db: ## Backup PostgreSQL database
	@echo "$(GREEN)Backing up database...$(NC)"
	docker exec -t chatico-mapper-postgres pg_dump -U chatico_user chatico_mapper > backup_$(shell date +%Y%m%d_%H%M%S).sql
	@echo "$(GREEN)Backup complete!$(NC)"

restore-db: ## Restore PostgreSQL database (usage: make restore-db FILE=backup.sql)
	@echo "$(YELLOW)Restoring database from $(FILE)...$(NC)"
	docker exec -i chatico-mapper-postgres psql -U chatico_user chatico_mapper < $(FILE)
	@echo "$(GREEN)Restore complete!$(NC)"

# ============================================================================
# Monitoring Commands
# ============================================================================

monitor: ## Monitor application logs
	cd docker && docker-compose logs -f app | grep -E "(ERROR|WARNING|INFO)"

monitor-webhooks: ## Monitor webhook processing
	cd docker && docker-compose logs -f app | grep -i webhook

watch-redis: ## Watch Redis cache activity
	docker exec -it chatico-mapper-redis redis-cli -a chatico_password MONITOR
