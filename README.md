# Strategy Tracker

A simple Go web application for tracking tactical asset allocation strategies.

## Strategies

- **GTAA AGG 6**: Top 6 assets by momentum with MA200 filter (6 equal slots)
- **GTAA AGG 3**: Top 3 assets by momentum with MA200 filter (3 equal slots)
- **Dual Momentum ROC12**: US vs International equity selection based on 12-month momentum

## Features

- Simple text-based web interface (no JavaScript)
- Responsive design (works on mobile and desktop)
- SQLite database for price history and signals
- Python scripts for data fetching from Tiingo API
- Automated signal generation via cron jobs

## Prerequisites

- Go 1.21+
- Python 3.10+
- Tiingo API key

## Setup

1. **Install Go dependencies:**
```bash
go mod download
```

2. **Install Python dependencies:**
```bash
pip install -r scripts/requirements.txt
```

3. **Set up configuration:**
```bash
cp config/config.example.yaml config/config.yaml
# Edit config.yaml and add your Tiingo API key
```

4. **Initialize database:**
```bash
sqlite3 data/strategies.db < db/schema.sql
python scripts/initialize_db.py
```

5. **Fetch initial data:**
```bash
python scripts/update_db.py
```

6. **Run the web server:**
```bash
go run main.go
```

Visit http://localhost:8080

## Cron Setup

Add to your crontab:

```bash
# Update prices daily at 6 AM ET
0 6 * * * cd /path/to/strategy-tracker && python scripts/update_db.py

# Generate monthly signals on last day of month
0 16 L * * cd /path/to/strategy-tracker && python scripts/calculate_signals.py
```

## Project Structure

```
strategy-tracker/
├── main.go              # Web server entry point
├── handlers/            # HTTP handlers for each page
├── templates/           # HTML templates
├── static/             # CSS files
├── db/                 # Database schema and queries
├── scripts/            # Python data pipeline
├── config/             # Configuration files
└── data/               # SQLite database
```

## Development

Run with live reload:
```bash
# Install air for hot reload
go install github.com/cosmtrek/air@latest

# Run with hot reload
air
```

## License

MIT
