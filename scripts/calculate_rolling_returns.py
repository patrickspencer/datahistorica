"""Calculate rolling period returns (1, 3, 5, 10 year) for all backtests."""

import sqlite3
import pandas as pd
from datetime import datetime, timedelta

def calculate_rolling_returns(monthly_values, dates, period_years):
    """Calculate best and worst CAGR for a rolling period."""
    # Convert to pandas Series
    values = pd.Series(monthly_values, index=pd.to_datetime(dates))

    # Calculate the number of months in the period
    period_months = period_years * 12

    best_cagr = float('-inf')
    worst_cagr = float('inf')
    best_start = None
    best_end = None
    worst_start = None
    worst_end = None

    # Iterate through all possible periods
    for i in range(len(values) - period_months):
        start_idx = i
        end_idx = i + period_months

        start_date = values.index[start_idx]
        end_date = values.index[end_idx]
        start_value = values.iloc[start_idx]
        end_value = values.iloc[end_idx]

        # Calculate CAGR for this period
        if start_value > 0:
            years = period_years
            cagr = ((end_value / start_value) ** (1 / years)) - 1

            if cagr > best_cagr:
                best_cagr = cagr
                best_start = start_date
                best_end = end_date

            if cagr < worst_cagr:
                worst_cagr = cagr
                worst_start = start_date
                worst_end = end_date

    if best_start is None:
        return None

    return {
        'best_cagr': float(best_cagr),
        'best_start_date': best_start.date().isoformat(),
        'best_end_date': best_end.date().isoformat(),
        'worst_cagr': float(worst_cagr),
        'worst_start_date': worst_start.date().isoformat(),
        'worst_end_date': worst_end.date().isoformat()
    }

def main():
    conn = sqlite3.connect('data/strategies.db')
    cursor = conn.cursor()

    # Clear existing rolling returns data
    cursor.execute("DELETE FROM backtest_rolling_returns")

    # Get all backtest configs
    cursor.execute("SELECT id, strategy_name, variant FROM backtest_configs")
    configs = cursor.fetchall()

    print("Calculating rolling returns for all backtests...")
    print("=" * 80)

    periods = [1, 3, 5, 10]

    for config_id, strategy_name, variant in configs:
        print(f"\n{strategy_name} - {variant} (ID: {config_id})")

        # Get monthly returns for this backtest (use after-tax values)
        cursor.execute("""
            SELECT date, after_tax_value
            FROM backtest_monthly_returns
            WHERE config_id = ?
            ORDER BY date ASC
        """, (config_id,))

        rows = cursor.fetchall()
        if not rows:
            print(f"  No monthly data found")
            continue

        dates = [row[0] for row in rows]
        values = [row[1] for row in rows]

        for period in periods:
            print(f"\n  {period}-Year Rolling Period:")

            result = calculate_rolling_returns(values, dates, period)

            if result is None:
                print(f"    Not enough data for {period}-year analysis")
                continue

            print(f"    Best:  {result['best_cagr']:>7.2%} | {result['best_start_date']} to {result['best_end_date']}")
            print(f"    Worst: {result['worst_cagr']:>7.2%} | {result['worst_start_date']} to {result['worst_end_date']}")

            # Insert into database
            cursor.execute("""
                INSERT INTO backtest_rolling_returns
                (config_id, period_years, best_cagr, best_start_date, best_end_date,
                 worst_cagr, worst_start_date, worst_end_date)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                config_id,
                period,
                result['best_cagr'],
                result['best_start_date'],
                result['best_end_date'],
                result['worst_cagr'],
                result['worst_start_date'],
                result['worst_end_date']
            ))

    conn.commit()
    conn.close()

    print("\n" + "=" * 80)
    print("✅ Rolling returns calculations complete and saved to database")

if __name__ == '__main__':
    main()
