.PHONY: help setup init update run clean test venv

PYTHON := python3
VENV := venv
VENV_PYTHON := $(VENV)/bin/python3
VENV_PIP := $(VENV)/bin/pip

help:
	@echo "Strategy Tracker - Available Commands:"
	@echo ""
	@echo "  make setup    - Install dependencies (Go + Python venv)"
	@echo "  make init     - Initialize database and fetch initial data"
	@echo "  make update   - Update prices and signals"
	@echo "  make run      - Run web server"
	@echo "  make clean    - Clean database and temp files"
	@echo "  make test     - Run tests"

venv:
	@echo "Creating Python virtual environment..."
	$(PYTHON) -m venv $(VENV)
	@echo "✅ Virtual environment created!"

setup: venv
	@echo "Installing Go dependencies..."
	go mod download
	@echo "Installing Python dependencies..."
	$(VENV_PIP) install --upgrade pip
	$(VENV_PIP) install -r scripts/requirements.txt
	@echo "✅ Setup complete!"

init:
	@echo "Initializing database..."
	@test -f config/config.yaml || (echo "❌ config/config.yaml not found. Copy config.example.yaml and add your API key." && exit 1)
	sqlite3 data/strategies.db < db/schema.sql
	cd scripts && ../$(VENV_PYTHON) initialize_db.py
	@echo "✅ Database initialized!"

update:
	@echo "Updating database..."
	cd scripts && ../$(VENV_PYTHON) update_db.py

run:
	@echo "Starting web server..."
	go run main.go

clean:
	@echo "Cleaning database..."
	rm -f data/strategies.db
	rm -f data/strategies.db-journal
	@echo "✅ Cleaned!"

test:
	@echo "Running tests..."
	go test ./...
