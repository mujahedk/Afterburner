.PHONY: up down logs reset seed demo sim help

API_URL = http://localhost:8000

help:
	@echo ""
	@echo "Afterburner — local demo commands"
	@echo ""
	@echo "  make up      Start the full stack (Postgres + API + worker)"
	@echo "  make down    Stop and remove containers"
	@echo "  make logs    Follow container logs"
	@echo "  make seed    Populate dashboard with demo jobs"
	@echo "  make demo    Run the guided demo scenario"
	@echo "  make sim     Run the 110-job failure simulation"
	@echo "  make reset   Clear all jobs from the database"
	@echo ""

up:
	docker compose up --build

down:
	docker compose down

logs:
	docker compose logs -f

seed:
	@bash scripts/seed.sh

demo:
	@bash scripts/demo.sh

sim:
	@pip install -q requests
	@python scripts/simulate_failures.py

reset:
	@curl -s -X POST $(API_URL)/admin/clear-jobs > /dev/null && echo "All jobs cleared." || echo "Error: is the API running? (make up)"
