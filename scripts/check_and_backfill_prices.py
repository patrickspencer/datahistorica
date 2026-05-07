#!/usr/bin/env python3
"""Check for missing price data on trading days and backfill gaps.

This script:
1. Gets expected trading days from NYSE calendar
2. Checks which days are missing in the database
3. Fetches missing data from Tiingo
4. Reports gaps that couldn't be filled
"""

import yaml
import os
import pandas as pd
import pandas_market_calendars as mcal
from datetime import datetime, timedelta
from pathlib import Path
from tiingo_client import TiingoClient
from db_utils import get_db_connection, ensure_ticker, insert_prices


def load_config():
    """Load configuration."""
    project_root = Path(__file__).parent.parent
    config_path = project_root / "config" / "config.yaml"

    with open(config_path, "r") as f:
        config = yaml.safe_load(f)

    if "TIINGO_API_KEY" in os.environ:
        config['tiingo']['api_key'] = os.environ['TIINGO_API_KEY']

    if not os.path.isabs(config['database']['path']):
        config['database']['path'] = str(project_root / config['database']['path'])

    return config


def get_expected_trading_days(start_date, end_date):
    """Get list of expected NYSE trading days."""
    nyse = mcal.get_calendar('NYSE')
    schedule = nyse.schedule(start_date=start_date, end_date=end_date)
    trading_days = schedule.index.strftime('%Y-%m-%d').tolist()
    return set(trading_days)


def get_existing_price_dates(conn, ticker_id):
    """Get dates we already have prices for."""
    cursor = conn.cursor()
    cursor.execute(
        "SELECT date FROM prices WHERE ticker_id = ? ORDER BY date",
        (ticker_id,)
    )
    dates = [row[0] for row in cursor.fetchall()]
    return set(dates)


def find_missing_days(ticker_symbol, ticker_id, conn, lookback_days=90):
    """Find trading days with missing price data."""
    # Get expected trading days for lookback period
    end_date = datetime.now()
    start_date = end_date - timedelta(days=lookback_days)

    expected_days = get_expected_trading_days(
        start_date.strftime('%Y-%m-%d'),
        end_date.strftime('%Y-%m-%d')
    )

    # Get days we have data for
    existing_days = get_existing_price_dates(conn, ticker_id)

    # Find missing days
    missing_days = sorted(expected_days - existing_days)

    return missing_days


def calculate_indicators_for_ticker(conn, ticker_id, ticker_symbol):
    """Recalculate MA200 and momentum indicators for a single ticker."""
    cursor = conn.cursor()

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
        print(f"    ⚠️  Only {len(rows)} days of data - need 200 for MA200")
        return False

    # Convert to pandas for calculation
    df = pd.DataFrame(rows, columns=['date', 'close'])
    df['date'] = pd.to_datetime(df['date'])
    df = df.set_index('date')
    df = df.sort_index()

    # Calculate MA200
    df['ma_200'] = df['close'].rolling(window=200).mean()

    # Calculate ROC at monthly intervals
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
    print(f"    📊 Recalculated {count} indicator values")
    return True


def backfill_missing_prices(config, ticker_symbol, ticker_id, missing_days, client, conn):
    """Fetch and insert missing price data."""
    if not missing_days:
        return 0

    # Group consecutive missing days into ranges for efficient API calls
    ranges = []
    if missing_days:
        start = missing_days[0]
        end = missing_days[0]

        for day in missing_days[1:]:
            # Convert to datetime for comparison
            current_day = pd.to_datetime(day)
            end_day = pd.to_datetime(end)

            # If gap is more than 7 days, start new range
            if (current_day - end_day).days > 7:
                ranges.append((start, end))
                start = day
            end = day

        ranges.append((start, end))

    # Fetch each range
    total_filled = 0
    for start_date, end_date in ranges:
        print(f"    Fetching {start_date} to {end_date}...", end=" ")
        prices = client.get_daily_prices(ticker_symbol, start_date=start_date, end_date=end_date)

        if prices:
            count = insert_prices(conn, ticker_id, prices)
            total_filled += count
            print(f"✓ {count} days")
        else:
            print("✗ No data available")

    return total_filled


def check_all_tickers(config, lookback_days=300):
    """Check all tickers for missing data and backfill.

    Default lookback of 300 days ensures we have complete data for MA200 calculation
    (200 trading days ≈ 280-290 calendar days).
    """
    print("=" * 70)
    print("CHECKING FOR MISSING PRICE DATA")
    print(f"Lookback period: {lookback_days} days (~{int(lookback_days * 0.71)} trading days)")
    print("=" * 70)
    print()

    client = TiingoClient(config['tiingo']['api_key'])
    conn = get_db_connection(config['database']['path'])

    # Get all unique tickers
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

    total_missing = 0
    total_filled = 0
    tickers_with_gaps = []

    for ticker in sorted(all_tickers):
        ticker_id = ensure_ticker(conn, ticker)

        # Find missing days
        missing_days = find_missing_days(ticker, ticker_id, conn, lookback_days)

        if missing_days:
            total_missing += len(missing_days)
            tickers_with_gaps.append(ticker)
            print(f"📉 {ticker}: Missing {len(missing_days)} days")
            print(f"    First missing: {missing_days[0]}, Last missing: {missing_days[-1]}")

            # Backfill
            filled = backfill_missing_prices(config, ticker, ticker_id, missing_days, client, conn)
            total_filled += filled

            # Recalculate indicators if we filled any gaps
            if filled > 0:
                calculate_indicators_for_ticker(conn, ticker_id, ticker)

            # Check if we still have gaps
            remaining = find_missing_days(ticker, ticker_id, conn, lookback_days)
            if remaining:
                print(f"    ⚠️  Still missing {len(remaining)} days (may not be available in Tiingo)")
            else:
                print(f"    ✅ All gaps filled!")
            print()
        else:
            print(f"✅ {ticker}: No missing days")

    conn.close()

    print()
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"Total tickers checked: {len(all_tickers)}")
    print(f"Tickers with gaps: {len(tickers_with_gaps)}")
    print(f"Total missing days found: {total_missing}")
    print(f"Total days backfilled: {total_filled}")

    if total_filled > 0:
        print(f"\n✅ Backfilled {total_filled} missing price records!")

    if total_missing > total_filled:
        print(f"\n⚠️  {total_missing - total_filled} days could not be backfilled (may not exist in Tiingo)")

    if tickers_with_gaps:
        print(f"\nTickers that had gaps: {', '.join(tickers_with_gaps)}")


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description='Check and backfill missing price data')
    parser.add_argument(
        '--lookback',
        type=int,
        default=300,
        help='Number of days to check back (default: 300, covers ~210 trading days for MA200)'
    )

    args = parser.parse_args()

    try:
        config = load_config()
        check_all_tickers(config, lookback_days=args.lookback)

    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        exit(1)


if __name__ == "__main__":
    main()
