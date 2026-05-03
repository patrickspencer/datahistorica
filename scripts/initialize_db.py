#!/usr/bin/env python3
"""Initialize database with strategy universes."""

import yaml
import os
from pathlib import Path
from db_utils import get_db_connection, add_strategy_universe, ensure_ticker


def load_config():
    """Load configuration."""
    # Get project root (parent of scripts directory)
    project_root = Path(__file__).parent.parent
    config_path = project_root / "config" / "config.yaml"

    with open(config_path, "r") as f:
        return yaml.safe_load(f)


def main():
    print("Initializing database...")

    config = load_config()

    # Get project root and make database path absolute
    project_root = Path(__file__).parent.parent
    db_path = config['database']['path']
    if not os.path.isabs(db_path):
        db_path = str(project_root / db_path)

    conn = get_db_connection(db_path)

    # Initialize GTAA 6 universe
    print("Setting up GTAA 6 universe...")
    gtaa6_tickers = config['strategies']['gtaa6']['universe']
    gtaa6_tickers.append(config['strategies']['gtaa6']['cash_ticker'])
    add_strategy_universe(conn, 'gtaa6', gtaa6_tickers)
    print(f"  Added {len(gtaa6_tickers)} tickers")

    # Initialize GTAA 3 universe (same as GTAA 6)
    print("Setting up GTAA 3 universe...")
    gtaa3_tickers = config['strategies']['gtaa3']['universe']
    gtaa3_tickers.append(config['strategies']['gtaa3']['cash_ticker'])
    add_strategy_universe(conn, 'gtaa3', gtaa3_tickers)
    print(f"  Added {len(gtaa3_tickers)} tickers")

    # Initialize Dual Momentum universe
    print("Setting up Dual Momentum universe...")
    dm_tickers = [
        config['strategies']['dual_momentum']['us_ticker'],
        config['strategies']['dual_momentum']['intl_ticker'],
        config['strategies']['dual_momentum']['cash_ticker'],
    ]
    add_strategy_universe(conn, 'dual_momentum', dm_tickers)
    print(f"  Added {len(dm_tickers)} tickers")

    conn.close()
    print("✅ Database initialized successfully!")


if __name__ == "__main__":
    main()
