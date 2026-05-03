"""Database utility functions."""

import sqlite3
from typing import List, Tuple, Optional
from datetime import datetime


def get_db_connection(db_path: str = "data/strategies.db") -> sqlite3.Connection:
    """Get database connection."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def ensure_ticker(conn: sqlite3.Connection, symbol: str, name: str = "", asset_class: str = "") -> int:
    """Ensure ticker exists in database, return ticker_id."""
    cursor = conn.cursor()

    # Check if exists
    cursor.execute("SELECT id FROM tickers WHERE symbol = ?", (symbol,))
    row = cursor.fetchone()

    if row:
        return row[0]

    # Insert new
    cursor.execute(
        "INSERT INTO tickers (symbol, name, asset_class) VALUES (?, ?, ?)",
        (symbol, name, asset_class)
    )
    conn.commit()
    return cursor.lastrowid


def insert_prices(conn: sqlite3.Connection, ticker_id: int, prices: List[dict]) -> int:
    """Insert or update price records."""
    cursor = conn.cursor()
    count = 0

    for price in prices:
        try:
            date = price['date'][:10]  # Extract YYYY-MM-DD
            cursor.execute(
                """
                INSERT OR REPLACE INTO prices
                (ticker_id, date, open, high, low, close, volume, adj_close)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    ticker_id,
                    date,
                    price.get('open'),
                    price.get('high'),
                    price.get('low'),
                    price['close'],
                    price.get('volume'),
                    price.get('adjClose', price['close'])
                )
            )
            count += 1
        except Exception as e:
            print(f"Error inserting price for {ticker_id} on {date}: {e}")

    conn.commit()
    return count


def cleanup_old_prices(conn: sqlite3.Connection, days_to_keep: int = 400):
    """Remove price data older than specified days."""
    cursor = conn.cursor()
    cutoff_date = (datetime.now() - timedelta(days=days_to_keep)).strftime("%Y-%m-%d")

    cursor.execute("DELETE FROM prices WHERE date < ?", (cutoff_date,))
    deleted = cursor.rowcount
    conn.commit()

    return deleted


def add_strategy_universe(conn: sqlite3.Connection, strategy_name: str, tickers: List[str]):
    """Add tickers to strategy universe."""
    cursor = conn.cursor()

    for symbol in tickers:
        ticker_id = ensure_ticker(conn, symbol)
        cursor.execute(
            "INSERT OR IGNORE INTO strategy_universes (strategy_name, ticker_id) VALUES (?, ?)",
            (strategy_name, ticker_id)
        )

    conn.commit()


def get_strategy_tickers(conn: sqlite3.Connection, strategy_name: str) -> List[Tuple[int, str]]:
    """Get all tickers for a strategy."""
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT t.id, t.symbol
        FROM tickers t
        JOIN strategy_universes su ON t.id = su.ticker_id
        WHERE su.strategy_name = ?
        ORDER BY t.symbol
        """,
        (strategy_name,)
    )
    return cursor.fetchall()


from datetime import timedelta
