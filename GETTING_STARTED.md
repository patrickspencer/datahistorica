# Getting Started with Strategy Tracker

## Quick Start (5 minutes)

### 1. Set Up Configuration

Copy the example config and add your Tiingo API key:

```bash
cd /Users/patrick/Dropbox/programming/strategy-tracker
cp config/config.example.yaml config/config.yaml
```

Edit `config/config.yaml` and replace `YOUR_API_KEY_HERE` with your actual Tiingo API key.

### 2. Install Dependencies

```bash
make setup
```

This installs:
- Go dependencies (sqlite3 driver)
- Python dependencies (requests, pandas, pyyaml)

### 3. Initialize Database

```bash
make init
```

This creates:
- SQLite database at `data/strategies.db`
- Strategy universe definitions (GTAA 6, GTAA 3, Dual Momentum)

### 4. Fetch Initial Data

```bash
make update
```

This will:
- Fetch 400 days of price history for all tickers from Tiingo
- Calculate MA200 and momentum indicators
- Generate current month's signals for all strategies

**Note:** This may take 2-3 minutes on first run (fetching ~40 tickers × 400 days).

### 5. Start the Web Server

```bash
make run
```

Visit http://localhost:8080 in your browser!

---

## What You'll See

The web interface shows:

1. **Home Page** - Overview of all 3 strategies with current holdings
2. **GTAA AGG 6** - Detailed view of 6-slot strategy
3. **GTAA AGG 3** - Detailed view of 3-slot strategy
4. **Dual Momentum** - US vs International selection

Each strategy shows:
- Current allocations
- Price vs MA200 status
- Momentum scores
- Signal date and last update

---

## Automated Updates (Cron)

To keep data fresh, add to your crontab:

```bash
crontab -e
```

Add this line (adjust path):

```bash
# Update strategy signals daily at 6 AM
0 6 * * * cd /Users/patrick/Dropbox/programming/strategy-tracker && make update >> logs/update.log 2>&1
```

Create logs directory:

```bash
mkdir -p logs
```

---

## Customization

### Change Tickers

Edit `config/config.yaml` to modify:
- GTAA universe (default: 14 ETFs)
- Dual Momentum tickers (default: VFINX, VGTSX, BIL)

Then re-run:

```bash
make clean
make init
make update
```

### Change Server Port

Set environment variable:

```bash
export PORT=3000
make run
```

Or edit `config/config.yaml`:

```yaml
server:
  port: 3000
```

### Use Environment Variable for API Key

Instead of putting API key in config file:

```bash
export TIINGO_API_KEY=your_key_here
make update
make run
```

---

## Troubleshooting

### "No signals found"

Run `make update` to generate signals.

### "Failed to open database"

Run `make init` to create the database.

### "Error fetching prices"

Check your Tiingo API key in `config/config.yaml`.

### Go module errors

```bash
go mod tidy
go mod download
```

### Python import errors

```bash
pip install --upgrade -r scripts/requirements.txt
```

---

## Development

### Live Reload (Go)

Install Air for hot reload:

```bash
go install github.com/cosmtrek/air@latest
```

Run with auto-reload:

```bash
air
```

### Manual Testing

Test individual components:

```bash
# Test price fetching only
cd scripts
python -c "from tiingo_client import TiingoClient; import yaml; c = yaml.safe_load(open('../config/config.yaml')); client = TiingoClient(c['tiingo']['api_key']); print(client.get_latest_price('SPY'))"

# Test database
sqlite3 data/strategies.db "SELECT * FROM tickers;"

# Test signal generation
cd scripts
python -c "import update_db; update_db.generate_signals(update_db.load_config())"
```

---

## Next Steps

1. **Review signals** - Check that current month's signals look correct
2. **Set up cron** - Automate daily updates
3. **Mobile test** - Visit site on phone to test responsive design
4. **Customize** - Adjust tickers, colors, or add new strategies

---

## Support

- Check `logs/update.log` for update errors
- Database browser: `sqlite3 data/strategies.db`
- Reset everything: `make clean && make init && make update`

Enjoy tracking your strategies!
