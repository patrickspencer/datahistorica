#!/usr/bin/env python3
"""Load GTAA AGG 6 V2 backtests into database.

V2 features:
- Proper after-tax compounding (not simple subtraction)
- 15 assets including QQQ + MTUM
- Two variants: Hold-Until-Replaced and Equal-Weight (both 200-day MA)
"""

import sqlite3
import pandas as pd
import json
from pathlib import Path
from datetime import datetime

# Database path
DB_PATH = Path(__file__).parent.parent / "data" / "strategies.db"

# Backtest result paths
BACKTEST_HOLD_DIR = Path("/Users/patrick/Dropbox/programming/tiingo_stocks_etfs/docs/strategy_results/gtaa_agg6_FINAL_TBILL_FIXED")
BACKTEST_EQWEIGHT_DIR = Path("/Users/patrick/Dropbox/programming/tiingo_stocks_etfs/docs/strategy_results/gtaa_agg6_equal_weight_PROPER")

# ETF Universe (15 assets)
ETF_UNIVERSE = [
    'GSG', 'IAU', 'VBK', 'VWO', 'VBR', 'VEA', 'VTV',
    'VCIT', 'VGIT', 'IGOV', 'EFA', 'QQQ', 'VNQ', 'MTUM', 'VGLT'
]


def clear_old_v2_backtests(conn):
    """Remove any existing v2 backtests."""
    cursor = conn.cursor()

    # Get IDs of v2 backtests
    cursor.execute("""
        SELECT id FROM backtest_configs
        WHERE strategy_name = 'gtaa6'
        AND variant IN ('v2_hold_until_replaced', 'v2_equal_weight')
    """)
    config_ids = [row[0] for row in cursor.fetchall()]

    if config_ids:
        placeholders = ','.join('?' * len(config_ids))

        # Delete related data
        cursor.execute(f"DELETE FROM backtest_annual_returns WHERE config_id IN ({placeholders})", config_ids)
        cursor.execute(f"DELETE FROM backtest_monthly_returns WHERE config_id IN ({placeholders})", config_ids)
        cursor.execute(f"DELETE FROM backtest_metrics WHERE config_id IN ({placeholders})", config_ids)
        cursor.execute(f"DELETE FROM backtest_configs WHERE id IN ({placeholders})", config_ids)

        print(f"✓ Cleared {len(config_ids)} old v2 backtest(s)")

    conn.commit()


def load_backtest(conn, variant, results_dir, description):
    """Load a single backtest into the database."""
    print(f"\n{'='*60}")
    print(f"Loading {variant}")
    print(f"{'='*60}")

    cursor = conn.cursor()

    # Read summary
    summary_df = pd.read_csv(results_dir / "summary_with_taxes.csv")
    summary = summary_df.iloc[0]

    # Read annual returns
    annual_df = pd.read_csv(results_dir / "annual_returns_with_taxes.csv")

    # Read monthly returns
    monthly_df = pd.read_csv(results_dir / "monthly_returns.csv")

    # Extract period info
    period_parts = summary['Period'].split(' to ')
    start_date = period_parts[0]
    end_date = period_parts[1]

    # Insert config
    cursor.execute("""
        INSERT INTO backtest_configs (
            strategy_name, variant, universe_etfs,
            start_date, end_date, initial_capital,
            rebalance_frequency, top_n, description
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        'gtaa6',
        variant,
        json.dumps(ETF_UNIVERSE),
        start_date,
        end_date,
        10000.0,
        'on_signal_change',
        6,
        description
    ))

    config_id = cursor.lastrowid
    print(f"✓ Created config (ID: {config_id})")

    # Insert metrics
    cursor.execute("""
        INSERT INTO backtest_metrics (
            config_id, period_start, period_end, years,
            pre_tax_cagr, after_tax_cagr, tax_drag,
            pre_tax_final, after_tax_final, total_taxes,
            effective_tax_rate, max_drawdown, num_transactions
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        config_id,
        start_date,
        end_date,
        summary['Years'],
        summary['Pre_Tax_CAGR'],
        summary['After_Tax_CAGR'],
        summary['Tax_Drag'],
        summary['Pre_Tax_Final'],
        summary['After_Tax_Final'],
        summary['Total_Taxes'],
        summary['Effective_Tax_Rate'],
        None,  # We'd need to calculate max drawdown from monthly data
        None   # We'd need to count transactions
    ))
    print(f"✓ Inserted metrics")

    # Insert annual returns
    for _, row in annual_df.iterrows():
        cursor.execute("""
            INSERT INTO backtest_annual_returns (
                config_id, year, pre_tax_return, after_tax_return,
                pre_tax_end, after_tax_end, tax_drag
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            config_id,
            int(row['Year']),
            row['Pre_Tax_Return'],
            row['After_Tax_Return'],
            row['Pre_Tax_End'],
            row['After_Tax_End'],
            row['Tax_Drag']
        ))
    print(f"✓ Inserted {len(annual_df)} annual returns")

    # Insert all monthly returns
    for idx, row in monthly_df.iterrows():
        cursor.execute("""
            INSERT INTO backtest_monthly_returns (
                config_id, date, pre_tax_value, after_tax_value,
                pre_tax_return, after_tax_return
            ) VALUES (?, ?, ?, ?, ?, ?)
        """, (
            config_id,
            row['Date'],
            row['Pre_Tax_Value'],
            row['After_Tax_Value'],
            row.get('Pre_Tax_Return', 0),
            row.get('After_Tax_Return', 0)
        ))
    print(f"✓ Inserted {len(monthly_df)} monthly returns")

    conn.commit()

    return config_id


def main():
    print("\n" + "="*60)
    print("GTAA AGG 6 V2 BACKTEST LOADER")
    print("="*60)

    conn = sqlite3.connect(DB_PATH)

    try:
        # Clear old v2 backtests
        clear_old_v2_backtests(conn)

        # Load Hold-Until-Replaced version
        load_backtest(
            conn,
            'v2_hold_until_replaced',
            BACKTEST_HOLD_DIR,
            'GTAA AGG 6 V2 - Hold Until Replaced (200-Day MA) | Proper after-tax compounding. 15 assets (Original 13 + QQQ + MTUM). Uses 200-day MA filter with 1,3,6,12-month ROC. Only trades when positions change.'
        )

        # Load Equal-Weight version
        load_backtest(
            conn,
            'v2_equal_weight',
            BACKTEST_EQWEIGHT_DIR,
            'GTAA AGG 6 V2 - Equal Weight Monthly Rebalancing (200-Day MA) | Proper after-tax compounding. 15 assets (Original 13 + QQQ + MTUM). Uses 200-day MA filter with 1,3,6,12-month ROC. Rebalances to 1/6 per position monthly.'
        )

        print("\n" + "="*60)
        print("✅ ALL BACKTESTS LOADED SUCCESSFULLY")
        print("="*60)

        # Show summary
        cursor = conn.cursor()
        cursor.execute("""
            SELECT c.variant, m.pre_tax_cagr, m.after_tax_cagr, m.tax_drag
            FROM backtest_configs c
            JOIN backtest_metrics m ON c.id = m.config_id
            WHERE c.strategy_name = 'gtaa6'
            AND c.variant IN ('v2_hold_until_replaced', 'v2_equal_weight')
            ORDER BY m.after_tax_cagr DESC
        """)

        print("\nLoaded backtests:")
        for row in cursor.fetchall():
            variant, pre_cagr, after_cagr, drag = row
            print(f"  {variant:15} Pre: {pre_cagr*100:5.2f}%  After: {after_cagr*100:5.2f}%  Drag: {drag*100:4.2f}%")

    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        conn.rollback()
        return 1
    finally:
        conn.close()

    return 0


if __name__ == "__main__":
    exit(main())
