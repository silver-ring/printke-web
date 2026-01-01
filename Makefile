.PHONY: help start stop restart logs ps build clean backup restore test

help:
	@echo "PrintKe Infrastructure - Management Commands"
	@echo ""
	@echo "Available commands:"
	@echo "  make start    - Start all services"
	@echo "  make stop     - Stop all services"
	@echo "  make restart  - Restart all services"
	@echo "  make logs     - View logs from all services"
	@echo "  make ps       - Show service status"
	@echo "  make build    - Build all Docker images"
	@echo "  make clean    - Stop services and remove volumes (DANGER)"
	@echo "  make backup   - Backup PostgreSQL database"
	@echo "  make restore  - Restore PostgreSQL database"
	@echo "  make test     - Run infrastructure tests"
	@echo ""

start:
	@./scripts/start.sh

stop:
	@./scripts/stop.sh

restart:
	@docker compose restart

logs:
	@docker compose logs -f

ps:
	@docker compose ps

build:
	@docker compose build

clean:
	@echo "WARNING: This will delete all volumes and data!"
	@read -p "Are you sure? [y/N] " -n 1 -r; \
	echo; \
	if [[ $$REPLY =~ ^[Yy]$$ ]]; then \
		docker compose down -v; \
	fi

backup:
	@./scripts/backup-db.sh

restore:
	@./scripts/restore-db.sh

test:
	@./scripts/test.sh
