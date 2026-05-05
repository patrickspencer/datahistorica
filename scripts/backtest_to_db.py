"""
Helper functions to store backtest results in the strategy-tracker database.

Usage:
    from backtest_to_db import save_backtest_results

    save_backtest_results(
        strategy_name='gtaa6',
        variant='equal_weight',
        monthly_df=monthly_df,
        annual_df=annual_df,
        metrics=metrics_dict,
        config=config_dict
    )
"""

import sqlite3
import json
from pathlib import Path


def get_db_connection(db_path='data/strategies.db'):
    """Get database connection."""
    return sqlite3.connect(db_path)


def insert_backtest_config(conn, strategy_name, variant, universe_etfs, start_date, end_date,
                           initial_capital=10000.0, rebalance_frequency='monthly',
                           top_n=None, description=None):
    """
    Insert or update backtest configuration.

    Returns: config_id
    """
    cursor = conn.cursor()

    # Convert universe_etfs list to JSON
    universe_json = json.dumps(universe_etfs) if isinstance(universe_etfs, list) else universe_etfs

    # Try to insert (or replace if exists)
    cursor.execute("""
        INSERT OR REPLACE INTO backtest_configs
        (strategy_name, variant, universe_etfs, start_date, end_date,
         initial_capital, rebalance_frequency, top_n, description)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (strategy_name, variant, universe_json, start_date, end_date,
          initial_capital, rebalance_frequency, top_n, description))

    conn.commit()

    # Get the config_id
    cursor.execute("""
        SELECT id FROM backtest_configs
        WHERE strategy_name = ? AND variant = ?
    """, (strategy_name, variant))

    return cursor.fetchone()[0]


def insert_monthly_returns(conn, config_id, monthly_df):
    """
    Insert monthly returns data.

    Expects monthly_df to have columns:
    - Date (index or column)
    - Pre_Tax_Value
    - After_Tax_Value
    - Pre_Tax_Return (optional)
    - After_Tax_Return (optional)
    - Tax_Paid_Cumulative
    - BIL_Weight (or cash allocation)
    - Holdings (comma-separated string or list)
    - Num_Holdings
    """
    cursor = conn.cursor()

    # Delete existing data for this config
    cursor.execute("DELETE FROM backtest_monthly_returns WHERE config_id = ?", (config_id,))

    # Prepare data
    df = monthly_df.copy()
    if 'Date' not in df.columns:
        df = df.reset_index()

    # Insert rows
    for _, row in df.iterrows():
        holdings_str = row.get('Holdings', '')
        if isinstance(holdings_str, list):
            holdings_str = ','.join(holdings_str)

        # Convert pandas Timestamp to string
        date_str = str(row['Date'])
        if hasattr(row['Date'], 'date'):
            date_str = row['Date'].date().isoformat()

        cursor.execute("""
            INSERT INTO backtest_monthly_returns
            (config_id, date, pre_tax_value, after_tax_value, pre_tax_return, after_tax_return,
             tax_paid_cumulative, cash_weight, holdings, num_holdings)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            config_id,
            date_str,
            row.get('Pre_Tax_Value'),
            row.get('After_Tax_Value'),
            row.get('Pre_Tax_Return'),
            row.get('After_Tax_Return'),
            row.get('Tax_Paid_Cumulative', 0),
            row.get('BIL_Weight', 0),
            holdings_str,
            row.get('Num_Holdings', 0)
        ))

    conn.commit()
    print(f"✅ Inserted {len(df)} monthly returns")


def insert_annual_returns(conn, config_id, annual_df):
    """
    Insert annual returns data.

    Expects annual_df to have columns:
    - Year
    - Pre_Tax_Return
    - After_Tax_Return
    - Tax_Drag
    - Pre_Tax_End
    - After_Tax_End
    """
    cursor = conn.cursor()

    # Delete existing data for this config
    cursor.execute("DELETE FROM backtest_annual_returns WHERE config_id = ?", (config_id,))

    # Insert rows
    for _, row in annual_df.iterrows():
        cursor.execute("""
            INSERT INTO backtest_annual_returns
            (config_id, year, pre_tax_return, after_tax_return, tax_drag,
             pre_tax_end, after_tax_end)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            config_id,
            int(row['Year']),
            row['Pre_Tax_Return'],
            row['After_Tax_Return'],
            row['Tax_Drag'],
            row['Pre_Tax_End'],
            row['After_Tax_End']
        ))

    conn.commit()
    print(f"✅ Inserted {len(annual_df)} annual returns")


def insert_metrics(conn, config_id, metrics):
    """
    Insert overall backtest metrics.

    Expects metrics dict with keys:
    - period_start, period_end, years
    - pre_tax_cagr, after_tax_cagr, tax_drag
    - pre_tax_final, after_tax_final
    - total_taxes, effective_tax_rate
    - max_drawdown (optional)
    - max_dd_peak_date, max_dd_trough_date, max_dd_recovery_date (optional)
    - max_dd_duration_months (optional)
    - num_transactions (optional)
    """
    cursor = conn.cursor()

    # Delete existing metrics for this config
    cursor.execute("DELETE FROM backtest_metrics WHERE config_id = ?", (config_id,))

    # Insert metrics
    cursor.execute("""
        INSERT INTO backtest_metrics
        (config_id, period_start, period_end, years,
         pre_tax_cagr, after_tax_cagr, tax_drag,
         pre_tax_final, after_tax_final, total_taxes, effective_tax_rate,
         max_drawdown, max_dd_peak_date, max_dd_trough_date, max_dd_recovery_date,
         max_dd_duration_months, num_transactions)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        config_id,
        metrics.get('period_start'),
        metrics.get('period_end'),
        metrics.get('years'),
        metrics.get('pre_tax_cagr'),
        metrics.get('after_tax_cagr'),
        metrics.get('tax_drag'),
        metrics.get('pre_tax_final'),
        metrics.get('after_tax_final'),
        metrics.get('total_taxes'),
        metrics.get('effective_tax_rate'),
        metrics.get('max_drawdown'),
        metrics.get('max_dd_peak_date'),
        metrics.get('max_dd_trough_date'),
        metrics.get('max_dd_recovery_date'),
        metrics.get('max_dd_duration_months'),
        metrics.get('num_transactions')
    ))

    conn.commit()
    print(f"✅ Inserted backtest metrics")


def save_backtest_results(strategy_name, variant, monthly_df, annual_df, metrics, config):
    """
    Complete function to save all backtest results to database.

    Parameters:
    - strategy_name: 'gtaa6', 'gtaa3', 'dual_momentum'
    - variant: 'equal_weight', 'hold_until_replaced'
    - monthly_df: DataFrame with monthly returns
    - annual_df: DataFrame with annual returns
    - metrics: dict with overall metrics
    - config: dict with configuration (universe_etfs, start_date, end_date, etc.)
    """
    conn = get_db_connection()

    try:
        print(f"\n{'='*80}")
        print(f"Saving {strategy_name} - {variant} to database")
        print(f"{'='*80}")

        # Insert config
        config_id = insert_backtest_config(
            conn,
            strategy_name=strategy_name,
            variant=variant,
            universe_etfs=config.get('universe_etfs', []),
            start_date=config.get('start_date'),
            end_date=config.get('end_date'),
            initial_capital=config.get('initial_capital', 10000.0),
            rebalance_frequency=config.get('rebalance_frequency', 'monthly'),
            top_n=config.get('top_n'),
            description=config.get('description')
        )
        print(f"✅ Config saved (ID: {config_id})")

        # Insert monthly returns
        insert_monthly_returns(conn, config_id, monthly_df)

        # Insert annual returns
        insert_annual_returns(conn, config_id, annual_df)

        # Insert metrics
        insert_metrics(conn, config_id, metrics)

        print(f"{'='*80}")
        print(f"✅ Successfully saved all data for {strategy_name} - {variant}")
        print(f"{'='*80}\n")

    except Exception as e:
        print(f"❌ Error saving backtest results: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == '__main__':
    # Test connection
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'backtest%'")
    tables = cursor.fetchall()
    print("Backtest tables:", tables)
    conn.close()
