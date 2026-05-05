"""
Copy historical mutual fund proxy data from tiingo_stocks_etfs to strategy-tracker.

This includes:
- VFINX (S&P 500 mutual fund) - proxy for SPY/MTUM
- VBMFX (Total Bond Market) - proxy for bond ETFs
- VGPMX (Precious Metals) - proxy for IAU
- PCRIX (Commodities) - proxy for GSG
- VISGX, VISVX, VIVAX, VEIEX, VGTSX - various equity proxies

Needed for backtesting before ETFs existed (pre-2000s).
"""

import sqlite3

# Source and target databases
SOURCE_DB = '../tiingo_stocks_etfs/data/strategies.db'
TARGET_DB = 'data/strategies.db'

# Proxy tickers to copy
PROXY_TICKERS = [
    'VFINX',  # S&P 500 mutual fund (SPY proxy)
    'VBMFX',  # Total Bond Market (bond ETF proxy)
    'VGPMX',  # Precious Metals (IAU proxy)
    'PCRIX',  # Commodities (GSG proxy)
    'VISGX',  # Small-cap growth (VBK proxy)
    'VISVX',  # Small-cap value (VBR proxy)
    'VIVAX',  # Large-cap value (VTV proxy)
    'VEIEX',  # Emerging markets (VWO proxy)
    'VGTSX',  # International developed (VEA proxy)
    'GLD',    # Gold (IAU proxy for 2004-2010)
]

def copy_proxy_data():
    """Copy ticker and price data for proxy mutual funds."""

    # Connect to both databases
    source_conn = sqlite3.connect(SOURCE_DB)
    target_conn = sqlite3.connect(TARGET_DB)

    source_cursor = source_conn.cursor()
    target_cursor = target_conn.cursor()

    total_prices = 0

    for ticker in PROXY_TICKERS:
        print(f"\nProcessing {ticker}...")

        # Get ticker info from source
        source_cursor.execute("""
            SELECT symbol, name, asset_class FROM tickers WHERE symbol = ?
        """, (ticker,))
        ticker_row = source_cursor.fetchone()

        if not ticker_row:
            print(f"  ⚠️ {ticker} not found in source database")
            continue

        symbol, name, asset_class = ticker_row

        # Insert ticker into target (or ignore if exists)
        target_cursor.execute("""
            INSERT OR IGNORE INTO tickers (symbol, name, asset_class)
            VALUES (?, ?, ?)
        """, (symbol, name, asset_class))

        # Get ticker_id from target
        target_cursor.execute("SELECT id FROM tickers WHERE symbol = ?", (symbol,))
        target_id = target_cursor.fetchone()[0]

        # Get source ticker_id
        source_cursor.execute("SELECT id FROM tickers WHERE symbol = ?", (symbol,))
        source_id = source_cursor.fetchone()[0]

        # Copy price data
        source_cursor.execute("""
            SELECT date, open, high, low, close, volume, adj_close
            FROM prices
            WHERE ticker_id = ?
            ORDER BY date
        """, (source_id,))

        prices = source_cursor.fetchall()

        if prices:
            # Insert prices into target (or ignore if exists)
            for price_row in prices:
                date, open_p, high, low, close, volume, adj_close = price_row
                target_cursor.execute("""
                    INSERT OR IGNORE INTO prices
                    (ticker_id, date, open, high, low, close, volume, adj_close)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (target_id, date, open_p, high, low, close, volume, adj_close))

            total_prices += len(prices)
            print(f"  ✅ Copied {len(prices)} price records")
        else:
            print(f"  ⚠️ No price data found")

    # Commit and close
    target_conn.commit()
    source_conn.close()
    target_conn.close()

    print(f"\n{'='*60}")
    print(f"✅ Copied {len(PROXY_TICKERS)} tickers, {total_prices} total price records")
    print(f"{'='*60}\n")


if __name__ == '__main__':
    copy_proxy_data()
