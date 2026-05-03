#!/usr/bin/env python3
"""Main update script - fetches prices, calculates indicators, and generates signals.

This script should be run daily via cron to keep the database up-to-date.
"""

import yaml
import os
import pandas as pd
from datetime import datetime, timedelta
from pathlib import Path
from tiingo_client import TiingoClient
from db_utils import (
    get_db_connection,
    ensure_ticker,
    insert_prices,
    get_strategy_tickers,
    cleanup_old_prices
)


def load_config():
    """Load configuration."""
    # Get project root (parent of scripts directory)
    project_root = Path(__file__).parent.parent
    config_path = project_root / "config" / "config.yaml"

    with open(config_path, "r") as f:
        config = yaml.safe_load(f)

    # Allow API key from environment
    if "TIINGO_API_KEY" in os.environ:
        config['tiingo']['api_key'] = os.environ['TIINGO_API_KEY']

    # Make database path absolute
    if not os.path.isabs(config['database']['path']):
        config['database']['path'] = str(project_root / config['database']['path'])

    return config


def fetch_prices(config):
    """Fetch latest prices for all tickers."""
    print("=" * 60)
    print("FETCHING PRICES FROM TIINGO")
    print("=" * 60)

    client = TiingoClient(config['tiingo']['api_key'])
    conn = get_db_connection(config['database']['path'])

    # Get all unique tickers across strategies
    all_tickers = set()
    for strategy_config in config['strategies'].values():
        if 'universe' in strategy_config:
            all_tickers.update(strategy_config['universe'])
            all_tickers.add(strategy_config.get('cash_ticker', 'BIL'))
        else:
            # Dual momentum
            all_tickers.add(strategy_config['us_ticker'])
            all_tickers.add(strategy_config['intl_ticker'])
            all_tickers.add(strategy_config['cash_ticker'])

    print(f"Fetching prices for {len(all_tickers)} tickers...")

    # Fetch historical data as far back as possible (2000 or ETF inception)
    start_date = "2000-01-01"
    end_date = datetime.now().strftime("%Y-%m-%d")

    for ticker in sorted(all_tickers):
        print(f"  {ticker}...", end=" ")
        ticker_id = ensure_ticker(conn, ticker)

        # Fetch all available historical data
        prices = client.get_daily_prices(ticker, start_date=start_date, end_date=end_date)

        if prices:
            count = insert_prices(conn, ticker_id, prices)
            print(f"✓ {count} days")
        else:
            print("✗ No data")

    # Don't cleanup old data - we want to keep historical data for backtesting
    # deleted = cleanup_old_prices(conn, days_to_keep=400)
    # if deleted > 0:
    #     print(f"Cleaned up {deleted} old price records")

    conn.close()
    print("✅ Price fetching complete!\n")


def calculate_indicators(config):
    """Calculate MA200 and momentum indicators."""
    print("=" * 60)
    print("CALCULATING INDICATORS")
    print("=" * 60)

    conn = get_db_connection(config['database']['path'])
    cursor = conn.cursor()

    # Get all tickers
    cursor.execute("SELECT id, symbol FROM tickers ORDER BY symbol")
    tickers = cursor.fetchall()

    for ticker_id, symbol in tickers:
        print(f"  {symbol}...", end=" ")

        # Get price history
        cursor.execute(
            """
            SELECT date, adj_close
            FROM prices
            WHERE ticker_id = ?
            ORDER BY date
            """,
            (ticker_id,)
        )
        rows = cursor.fetchall()

        if len(rows) < 200:
            print(f"✗ Insufficient data ({len(rows)} days)")
            continue

        # Convert to pandas for easy calculation
        df = pd.DataFrame(rows, columns=['date', 'close'])
        df['date'] = pd.to_datetime(df['date'])
        df = df.set_index('date')
        df = df.sort_index()

        # Calculate MA200
        df['ma_200'] = df['close'].rolling(window=200).mean()

        # Calculate ROC at monthly intervals (approximate)
        df_monthly = df.resample('ME').last()
        df_monthly['roc_1m'] = df_monthly['close'].pct_change(1)
        df_monthly['roc_3m'] = df_monthly['close'].pct_change(3)
        df_monthly['roc_6m'] = df_monthly['close'].pct_change(6)
        df_monthly['roc_12m'] = df_monthly['close'].pct_change(12)
        df_monthly['avg_roc'] = (
            df_monthly['roc_1m'] +
            df_monthly['roc_3m'] +
            df_monthly['roc_6m'] +
            df_monthly['roc_12m']
        ) / 4.0

        # Join monthly ROC back to daily data (forward fill)
        df = df.join(df_monthly[['roc_1m', 'roc_3m', 'roc_6m', 'roc_12m', 'avg_roc']], how='left')
        df = df.ffill()

        # Insert indicators
        count = 0
        for date, row in df.iterrows():
            if pd.notna(row['ma_200']):
                cursor.execute(
                    """
                    INSERT OR REPLACE INTO indicators
                    (ticker_id, date, ma_200, roc_1m, roc_3m, roc_6m, roc_12m, avg_roc)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        ticker_id,
                        date.strftime('%Y-%m-%d'),
                        row['ma_200'],
                        row.get('roc_1m'),
                        row.get('roc_3m'),
                        row.get('roc_6m'),
                        row.get('roc_12m'),
                        row.get('avg_roc'),
                    )
                )
                count += 1

        conn.commit()
        print(f"✓ {count} indicators")

    conn.close()
    print("✅ Indicator calculation complete!\n")


def generate_signals(config):
    """Generate strategy signals for latest month."""
    print("=" * 60)
    print("GENERATING STRATEGY SIGNALS")
    print("=" * 60)

    conn = get_db_connection(config['database']['path'])

    # Get last business day of current month
    today = datetime.now()
    signal_date = (today.replace(day=1) + timedelta(days=32)).replace(day=1) - timedelta(days=1)

    # Adjust to last available trading day
    cursor = conn.cursor()
    cursor.execute("SELECT MAX(date) FROM prices")
    last_price_date = cursor.fetchone()[0]
    signal_date = min(signal_date.strftime('%Y-%m-%d'), last_price_date)

    print(f"Signal date: {signal_date}\n")

    # Generate GTAA 6 signals
    generate_gtaa_signals(conn, 'gtaa6', config['strategies']['gtaa6'], signal_date)

    # Generate GTAA 3 signals
    generate_gtaa_signals(conn, 'gtaa3', config['strategies']['gtaa3'], signal_date)

    # Generate Dual Momentum signals
    generate_dual_momentum_signals(conn, config['strategies']['dual_momentum'], signal_date)

    conn.close()
    print("✅ Signal generation complete!\n")


def generate_gtaa_signals(conn, strategy_name, strategy_config, signal_date):
    """Generate GTAA strategy signals."""
    print(f"Generating {strategy_name} signals...")

    cursor = conn.cursor()
    top_n = strategy_config['top_n']
    slot_allocation = 1.0 / top_n

    # Get universe tickers
    tickers = get_strategy_tickers(conn, strategy_name)

    # Get latest indicators for each ticker
    signals = []
    for ticker_id, symbol in tickers:
        if symbol == strategy_config['cash_ticker']:
            continue  # Skip cash in universe

        cursor.execute(
            """
            SELECT p.adj_close, i.ma_200, i.avg_roc
            FROM prices p
            LEFT JOIN indicators i ON p.ticker_id = i.ticker_id AND p.date = i.date
            WHERE p.ticker_id = ? AND p.date <= ?
            ORDER BY p.date DESC
            LIMIT 1
            """,
            (ticker_id, signal_date)
        )
        row = cursor.fetchone()

        if row:
            price, ma_200, avg_roc = row
            above_ma = price > ma_200 if ma_200 else False

            signals.append({
                'ticker_id': ticker_id,
                'symbol': symbol,
                'price': price,
                'ma_200': ma_200,
                'avg_roc': avg_roc or 0.0,
                'above_ma': above_ma,
            })

    # Sort by momentum and take top N
    signals.sort(key=lambda x: x['avg_roc'], reverse=True)
    top_signals = signals[:top_n]

    # Create strategy signal record
    cursor.execute(
        "INSERT OR REPLACE INTO strategy_signals (strategy_name, signal_date) VALUES (?, ?)",
        (strategy_name, signal_date)
    )
    signal_id = cursor.lastrowid

    # Create holdings
    qualifying_count = sum(1 for s in top_signals if s['above_ma'])
    cash_slots = top_n - qualifying_count

    for i, signal in enumerate(top_signals):
        if signal['above_ma']:
            cursor.execute(
                """
                INSERT INTO holdings
                (signal_id, ticker_id, allocation, is_cash, price, ma_200, momentum_score, reason)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    signal_id,
                    signal['ticker_id'],
                    slot_allocation,
                    False,
                    signal['price'],
                    signal['ma_200'],
                    signal['avg_roc'],
                    f"Rank #{i+1} by momentum, above MA200"
                )
            )
            print(f"  ✓ {signal['symbol']}: {slot_allocation*100:.1f}% (above MA200)")
        else:
            print(f"  ✗ {signal['symbol']}: Below MA200, slot → cash")

    # Add cash holdings if any
    if cash_slots > 0:
        cash_ticker_id = ensure_ticker(conn, strategy_config['cash_ticker'])
        cursor.execute(
            """
            INSERT INTO holdings
            (signal_id, ticker_id, allocation, is_cash, reason)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                signal_id,
                cash_ticker_id,
                slot_allocation * cash_slots,
                True,
                f"{cash_slots} slot(s) defensive"
            )
        )
        print(f"  🛡️  BIL: {slot_allocation * cash_slots * 100:.1f}% ({cash_slots} slots)")

    conn.commit()
    print(f"✅ {strategy_name} complete\n")


def generate_dual_momentum_signals(conn, strategy_config, signal_date):
    """Generate dual momentum signals."""
    print("Generating dual_momentum signals...")

    cursor = conn.cursor()

    # Get US ticker data
    us_ticker = strategy_config['us_ticker']
    us_ticker_id = ensure_ticker(conn, us_ticker)

    cursor.execute(
        """
        SELECT p.adj_close, i.roc_12m
        FROM prices p
        LEFT JOIN indicators i ON p.ticker_id = i.ticker_id AND p.date = i.date
        WHERE p.ticker_id = ? AND p.date <= ?
        ORDER BY p.date DESC
        LIMIT 1
        """,
        (us_ticker_id, signal_date)
    )
    us_data = cursor.fetchone()

    # Get International ticker data
    intl_ticker = strategy_config['intl_ticker']
    intl_ticker_id = ensure_ticker(conn, intl_ticker)

    cursor.execute(
        """
        SELECT p.adj_close, i.roc_12m
        FROM prices p
        LEFT JOIN indicators i ON p.ticker_id = i.ticker_id AND p.date = i.date
        WHERE p.ticker_id = ? AND p.date <= ?
        ORDER BY p.date DESC
        LIMIT 1
        """,
        (intl_ticker_id, signal_date)
    )
    intl_data = cursor.fetchone()

    if not us_data or not intl_data:
        print("  ✗ Insufficient data")
        return

    us_price, us_roc = us_data
    intl_price, intl_roc = intl_data

    us_roc = us_roc or 0.0
    intl_roc = intl_roc or 0.0

    # Determine selection
    us_positive = us_roc > 0
    intl_positive = intl_roc > 0

    if us_positive and intl_positive:
        # Both positive: choose best
        if us_roc > intl_roc:
            selected_id = us_ticker_id
            selected_symbol = us_ticker
            selected_price = us_price
            selected_roc = us_roc
            reason = f"Both positive, US ROC ({us_roc*100:.2f}%) > INTL ({intl_roc*100:.2f}%)"
        else:
            selected_id = intl_ticker_id
            selected_symbol = intl_ticker
            selected_price = intl_price
            selected_roc = intl_roc
            reason = f"Both positive, INTL ROC ({intl_roc*100:.2f}%) > US ({us_roc*100:.2f}%)"
        is_cash = False
    elif us_positive:
        selected_id = us_ticker_id
        selected_symbol = us_ticker
        selected_price = us_price
        selected_roc = us_roc
        reason = f"Only US positive (ROC: {us_roc*100:.2f}%)"
        is_cash = False
    elif intl_positive:
        selected_id = intl_ticker_id
        selected_symbol = intl_ticker
        selected_price = intl_price
        selected_roc = intl_roc
        reason = f"Only INTL positive (ROC: {intl_roc*100:.2f}%)"
        is_cash = False
    else:
        # Both negative: go to cash
        cash_ticker = strategy_config['cash_ticker']
        selected_id = ensure_ticker(conn, cash_ticker)
        selected_symbol = cash_ticker
        selected_price = None
        selected_roc = None
        reason = f"Both negative: US ({us_roc*100:.2f}%), INTL ({intl_roc*100:.2f}%)"
        is_cash = True

    # Create signal
    cursor.execute(
        "INSERT OR REPLACE INTO strategy_signals (strategy_name, signal_date) VALUES (?, ?)",
        ('dual_momentum', signal_date)
    )
    signal_id = cursor.lastrowid

    # Create holding
    cursor.execute(
        """
        INSERT INTO holdings
        (signal_id, ticker_id, allocation, is_cash, price, momentum_score, reason)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            signal_id,
            selected_id,
            1.0,
            is_cash,
            selected_price,
            selected_roc,
            reason
        )
    )

    conn.commit()

    if is_cash:
        print(f"  🛡️  {selected_symbol}: 100% (defensive)")
    else:
        print(f"  ✓ {selected_symbol}: 100% (ROC: {selected_roc*100:.2f}%)")

    print("✅ dual_momentum complete\n")


def main():
    """Main update workflow."""
    print("\n" + "=" * 60)
    print("STRATEGY TRACKER - DATABASE UPDATE")
    print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60 + "\n")

    try:
        config = load_config()

        # Step 1: Fetch prices
        fetch_prices(config)

        # Step 2: Calculate indicators
        calculate_indicators(config)

        # Step 3: Generate signals
        generate_signals(config)

        print("=" * 60)
        print("✅ ALL UPDATES COMPLETE!")
        print("=" * 60)

    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        exit(1)


if __name__ == "__main__":
    main()
