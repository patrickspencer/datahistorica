#!/usr/bin/env python3
"""One-time migration: fetch SPMO data, remove MTUM from strategy universes."""

import sys
import yaml
import os
import pandas as pd
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from tiingo_client import TiingoClient
from db_utils import get_db_connection, ensure_ticker, insert_prices


def load_config():
    project_root = Path(__file__).parent.parent
    config_path = project_root / "config" / "config.yaml"
    with open(config_path, "r") as f:
        config = yaml.safe_load(f)
    if not os.path.isabs(config['database']['path']):
        config['database']['path'] = str(project_root / config['database']['path'])
    return config


def fetch_and_store_ticker(conn, client, symbol, start_date, end_date):
    ticker_id = ensure_ticker(conn, symbol)
    prices = client.get_daily_prices(symbol, start_date=start_date, end_date=end_date)
    if prices:
        count = insert_prices(conn, ticker_id, prices)
        print(f"  {symbol}: {count} price rows inserted")
    else:
        print(f"  {symbol}: no data returned from Tiingo")
    return ticker_id


def calculate_indicators(conn, ticker_id, symbol):
    cursor = conn.cursor()
    cursor.execute(
        "SELECT date, adj_close FROM prices WHERE ticker_id = ? ORDER BY date",
        (ticker_id,)
    )
    rows = cursor.fetchall()

    if len(rows) < 200:
        print(f"  {symbol}: only {len(rows)} days of data, skipping indicators")
        return

    df = pd.DataFrame(rows, columns=['date', 'close'])
    df['date'] = pd.to_datetime(df['date'])
    df = df.set_index('date').sort_index()

    df['ma_200'] = df['close'].rolling(window=200).mean()
    df['ma_215'] = df['close'].rolling(window=215).mean()

    df_monthly = df.resample('ME').last()
    df_monthly['roc_1m'] = df_monthly['close'].pct_change(1)
    df_monthly['roc_3m'] = df_monthly['close'].pct_change(3)
    df_monthly['roc_6m'] = df_monthly['close'].pct_change(6)
    df_monthly['roc_12m'] = df_monthly['close'].pct_change(12)
    df_monthly['avg_roc'] = (
        df_monthly['roc_1m'] + df_monthly['roc_3m'] +
        df_monthly['roc_6m'] + df_monthly['roc_12m']
    ) / 4.0

    df = df.join(df_monthly[['roc_1m', 'roc_3m', 'roc_6m', 'roc_12m', 'avg_roc']], how='left')
    df = df.ffill()

    count = 0
    for date, row in df.iterrows():
        if pd.notna(row['ma_200']):
            cursor.execute("""
                INSERT OR REPLACE INTO indicators
                (ticker_id, date, ma_200, ma_215, roc_1m, roc_3m, roc_6m, roc_12m, avg_roc)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                ticker_id,
                date.strftime('%Y-%m-%d'),
                row['ma_200'], row.get('ma_215'),
                row.get('roc_1m'), row.get('roc_3m'),
                row.get('roc_6m'), row.get('roc_12m'),
                row.get('avg_roc'),
            ))
            count += 1
    conn.commit()
    print(f"  {symbol}: {count} indicator rows written")


def remove_from_strategy_universes(conn, symbol, strategy_names):
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM tickers WHERE symbol = ?", (symbol,))
    row = cursor.fetchone()
    if not row:
        print(f"  {symbol}: not found in tickers table, nothing to remove")
        return
    ticker_id = row[0]
    for strategy in strategy_names:
        cursor.execute(
            "DELETE FROM strategy_universes WHERE strategy_name = ? AND ticker_id = ?",
            (strategy, ticker_id)
        )
        print(f"  Removed {symbol} from {strategy} universe ({cursor.rowcount} rows deleted)")
    conn.commit()


def main():
    config = load_config()
    conn = get_db_connection(config['database']['path'])
    client = TiingoClient(config['tiingo']['api_key'])

    start_date = "2000-01-01"
    end_date = datetime.now().strftime("%Y-%m-%d")

    print("=== Fetching SPMO price data ===")
    spmo_id = fetch_and_store_ticker(conn, client, "SPMO", start_date, end_date)

    print("\n=== Calculating SPMO indicators ===")
    calculate_indicators(conn, spmo_id, "SPMO")

    print("\n=== Removing MTUM from strategy universes ===")
    remove_from_strategy_universes(conn, "MTUM", ["gtaa6", "gtaa3"])

    conn.close()
    print("\nDone.")


if __name__ == "__main__":
    main()
