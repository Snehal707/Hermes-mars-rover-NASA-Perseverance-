# HERMES Mars Rover — Makefile
REPO_ROOT := $(dir $(abspath $(lastword $(MAKEFILE_LIST))))

.PHONY: setup sim bridge api gateway telegram dashboard all stop test clean

setup:
	@echo "Installing Python dependencies..."
	@if [ -f requirements.txt ]; then pip install -r requirements.txt; else echo "No requirements.txt found. Run: pip install fastapi uvicorn aiohttp pydantic aiohttp python-telegram-bot"; fi
	@pip install pytest pytest-asyncio httpx 2>/dev/null || true
	@echo "Installing dashboard deps..."
	@cd dashboard 2>/dev/null && npm install || true
	@echo "Setup complete. Configure .env and Hermes (hermes setup)."

sim:
	cd "$(REPO_ROOT)" && ./scripts/start_sim.sh

bridge:
	cd "$(REPO_ROOT)" && ./scripts/start_bridge.sh

api:
	cd "$(REPO_ROOT)" && ./scripts/start_api.sh

telegram:
	@echo "make telegram is an alias to gateway mode (single Telegram poller)."
	cd "$(REPO_ROOT)" && ./scripts/start_gateway_pdf.sh

gateway:
	cd "$(REPO_ROOT)" && ./scripts/start_gateway_pdf.sh

dashboard:
	cd "$(REPO_ROOT)/dashboard" && npm run dev

all:
	cd "$(REPO_ROOT)" && ./scripts/start_all.sh

stop:
	@echo "Stopping services..."
	@-lsof -ti:8000 | xargs kill -9 2>/dev/null || true
	@-lsof -ti:8765 | xargs kill -9 2>/dev/null || true
	@-pkill -f "telegram_bot.bot" 2>/dev/null || true
	@-pkill -f "hermes_cli.main gateway run" 2>/dev/null || true
	@-pkill -f "hermes_rover/gateway_agent.py" 2>/dev/null || true
	@-pkill -f "gz sim" 2>/dev/null || true
	@echo "Services stopped."

test:
	cd "$(REPO_ROOT)" && PYTHONPATH=. pytest tests/ -v

clean:
	@echo "Cleaning..."
	@rm -rf dashboard/.next 2>/dev/null || true
	@find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	@find . -type f -name "*.pyc" -delete 2>/dev/null || true
	@echo "Clean complete."
