"""Dual Momentum with MA200 Filter

Uses 200-day moving average to filter, then average ROC to select between US and International.

Selection Logic:
1. If both above MA200: Choose asset with best average ROC (1, 3, 6, 12 months)
2. If only one above MA200: Choose that asset
3. If both below MA200: Go to T-bills

Assets:
- US: VFINX (1995-2026)
- International: VGTSX (1996-2026)
- Cash: VBMFX (1995-2007), BIL (2007-2026)
"""

import sys
import sqlite3
import pandas as pd
from pathlib import Path
from datetime import datetime

# Add lib directory to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'lib'))
from portfolio import Portfolio, SHORT_TERM_TAX_RATE, LONG_TERM_TAX_RATE

# Add scripts directory to path for backtest_to_db
sys.path.insert(0, str(Path(__file__).parent))
from backtest_to_db import save_backtest_results

# Main backtest
START_DATE = '1996-01-01'
END_DATE = '2026-05-01'
INITIAL_CAPITAL = 10000.0

print("="*100)
print("DUAL MOMENTUM WITH MA200 FILTER")
print("="*100)
print()

# Load data
conn = sqlite3.connect('data/strategies.db')

# Load US equity (VFINX - S&P 500 mutual fund)
us_query = f"""
    SELECT p.date, p.adj_close as close FROM prices p
    JOIN tickers t ON p.ticker_id = t.id
    WHERE t.symbol = 'VFINX'
      AND p.date >= '{START_DATE}' AND p.date <= '{END_DATE}'
    ORDER BY p.date
"""
us_df = pd.read_sql_query(us_query, conn)
us_df['date'] = pd.to_datetime(us_df['date'])
us_df = us_df.set_index('date')

# Load International equity (VGTSX - Total International mutual fund)
intl_query = f"""
    SELECT p.date, p.adj_close as close FROM prices p
    JOIN tickers t ON p.ticker_id = t.id
    WHERE t.symbol = 'VGTSX'
      AND p.date >= '{START_DATE}' AND p.date <= '{END_DATE}'
    ORDER BY p.date
"""
intl_df = pd.read_sql_query(intl_query, conn)
intl_df['date'] = pd.to_datetime(intl_df['date'])
intl_df = intl_df.set_index('date')

# Load T-bills (VBMFX before 2007, BIL after)
tbill_pre_query = f"""
    SELECT p.date, p.adj_close as close FROM prices p
    JOIN tickers t ON p.ticker_id = t.id
    WHERE t.symbol = 'VBMFX' AND p.date >= '{START_DATE}' AND p.date < '2007-05-30'
    ORDER BY p.date
"""
tbill_pre_df = pd.read_sql_query(tbill_pre_query, conn)
if len(tbill_pre_df) > 0:
    tbill_pre_df['date'] = pd.to_datetime(tbill_pre_df['date'])
    tbill_pre_df = tbill_pre_df.set_index('date')
else:
    tbill_pre_df = pd.DataFrame()

tbill_post_query = f"""
    SELECT p.date, p.adj_close as close FROM prices p
    JOIN tickers t ON p.ticker_id = t.id
    WHERE t.symbol = 'BIL' AND p.date >= '2007-05-30' AND p.date <= '{END_DATE}'
    ORDER BY p.date
"""
tbill_post_df = pd.read_sql_query(tbill_post_query, conn)
if len(tbill_post_df) > 0:
    tbill_post_df['date'] = pd.to_datetime(tbill_post_df['date'])
    tbill_post_df = tbill_post_df.set_index('date')
else:
    tbill_post_df = pd.DataFrame()

conn.close()

# Combine T-bill data
tbill_combined = pd.concat([tbill_pre_df, tbill_post_df])

# Create price dataframe
price_df = pd.DataFrame({
    'US': us_df['close'],
    'INTL': intl_df['close'],
    'CASH': tbill_combined['close']
}).ffill()

print(f"Data loaded: {price_df.index[0].date()} to {price_df.index[-1].date()}")
print(f"Total days: {len(price_df)}")
print()

# Calculate MA200
ma_200 = price_df[['US', 'INTL']].rolling(window=200).mean()

# Get month-end dates
month_ends = price_df.resample('ME').last().index
monthly_prices = price_df.reindex(month_ends, method='ffill')

# Calculate ROC for momentum
roc_1m = monthly_prices.pct_change(1)
roc_3m = monthly_prices.pct_change(3)
roc_6m = monthly_prices.pct_change(6)
roc_12m = monthly_prices.pct_change(12)
avg_roc = (roc_1m + roc_3m + roc_6m + roc_12m) / 4

# Initialize portfolios
pre_tax_portfolio = Portfolio(INITIAL_CAPITAL)
after_tax_portfolio = Portfolio(INITIAL_CAPITAL)

monthly_data = []

for i, signal_date in enumerate(month_ends):
    if i < 12:  # Need 12 months for ROC calculation
        continue

    # Find actual trading date (month-end might not exist)
    if signal_date not in price_df.index:
        trading_date = price_df.index[price_df.index <= signal_date][-1]
    else:
        trading_date = signal_date

    # Get current prices and MA200 values
    current_prices = price_df.loc[trading_date]
    ma_200_values = ma_200.loc[trading_date]

    # Get momentum scores (use signal_date from monthly data)
    momentum_scores = avg_roc.loc[signal_date]

    # Determine which assets are above MA200
    us_above_ma = current_prices['US'] > ma_200_values['US']
    intl_above_ma = current_prices['INTL'] > ma_200_values['INTL']

    # Selection logic
    if us_above_ma and intl_above_ma:
        # Both above: choose best momentum
        if momentum_scores['US'] > momentum_scores['INTL']:
            selected = 'US'
        else:
            selected = 'INTL'
    elif us_above_ma:
        # Only US above
        selected = 'US'
    elif intl_above_ma:
        # Only INTL above
        selected = 'INTL'
    else:
        # Both below: go to cash
        selected = 'CASH'

    # Rebalance both portfolios
    for portfolio in [pre_tax_portfolio, after_tax_portfolio]:
        # Sell all current positions
        for ticker in ['US', 'INTL', 'CASH']:
            if portfolio.get_total_shares(ticker) > 0:
                portfolio.sell_all(ticker, current_prices[ticker], signal_date)

        # Buy selected position with all cash
        portfolio_value = portfolio.cash
        shares = portfolio_value / current_prices[selected]
        portfolio.buy(selected, shares, current_prices[selected], signal_date)

    # Year-end taxes
    year_end = signal_date.month == 12 or i == len(month_ends) - 1
    if year_end:
        prices_dict = current_prices.to_dict()
        after_tax_portfolio.calculate_year_end_taxes(prices_dict, signal_date)

    # Calculate portfolio values
    prices_dict = current_prices.to_dict()
    pre_tax_value = pre_tax_portfolio.get_portfolio_value(prices_dict)
    after_tax_value = after_tax_portfolio.get_portfolio_value(prices_dict)

    # Track data
    monthly_data.append({
        'Date': signal_date,
        'Selection': selected,
        'US_Above_MA': us_above_ma,
        'INTL_Above_MA': intl_above_ma,
        'US_Momentum': momentum_scores['US'],
        'INTL_Momentum': momentum_scores['INTL'],
        'Pre_Tax_Value': pre_tax_value,
        'After_Tax_Value': after_tax_value,
        'Tax_Paid_Cumulative': after_tax_portfolio.taxes_paid,
    })

# Calculate metrics
monthly_df = pd.DataFrame(monthly_data).set_index('Date')
monthly_df['Pre_Tax_Return'] = monthly_df['Pre_Tax_Value'].pct_change()
monthly_df['After_Tax_Return'] = monthly_df['After_Tax_Value'].pct_change()
monthly_df['Year'] = monthly_df.index.year

# Annual summary
annual_data = []
for year in sorted(monthly_df['Year'].unique()):
    year_df = monthly_df[monthly_df['Year'] == year]
    if len(year_df) < 2:
        continue

    pre_tax_start = year_df['Pre_Tax_Value'].iloc[0]
    pre_tax_end = year_df['Pre_Tax_Value'].iloc[-1]
    after_tax_start = year_df['After_Tax_Value'].iloc[0]
    after_tax_end = year_df['After_Tax_Value'].iloc[-1]

    pre_tax_return = (pre_tax_end / pre_tax_start) - 1
    after_tax_return = (after_tax_end / after_tax_start) - 1

    annual_data.append({
        'Year': int(year),
        'Pre_Tax_Return': pre_tax_return,
        'After_Tax_Return': after_tax_return,
        'Tax_Drag': pre_tax_return - after_tax_return,
        'Pre_Tax_End': pre_tax_end,
        'After_Tax_End': after_tax_end,
    })

annual_df = pd.DataFrame(annual_data)

# Overall metrics
years = (monthly_df.index[-1] - monthly_df.index[0]).days / 365.25
pre_tax_final = monthly_df['Pre_Tax_Value'].iloc[-1]
after_tax_final = monthly_df['After_Tax_Value'].iloc[-1]

pre_tax_cagr = (pre_tax_final / INITIAL_CAPITAL) ** (1.0 / years) - 1
after_tax_cagr = (after_tax_final / INITIAL_CAPITAL) ** (1.0 / years) - 1
tax_drag = pre_tax_cagr - after_tax_cagr

print("="*100)
print("RESULTS")
print("="*100)
print()
print(f"Period: {monthly_df.index[0].date()} to {monthly_df.index[-1].date()} ({years:.2f} years)")
print()
print(f"{'Metric':<30} {'Pre-Tax':<20} {'After-Tax':<20} {'Difference':<15}")
print("-"*85)
print(f"{'Final Value ($10k)':<30} ${pre_tax_final:>18,.2f} ${after_tax_final:>18,.2f} ${pre_tax_final - after_tax_final:>13,.2f}")
print(f"{'Total Return':<30} {(pre_tax_final/INITIAL_CAPITAL - 1):>18.1%} {(after_tax_final/INITIAL_CAPITAL - 1):>18.1%} {(pre_tax_final - after_tax_final)/INITIAL_CAPITAL:>13.1%}")
print(f"{'CAGR':<30} {pre_tax_cagr:>18.2%} {after_tax_cagr:>18.2%} {tax_drag:>13.2%}")
print()
print(f"Total taxes paid: ${after_tax_portfolio.taxes_paid:,.2f}")
if pre_tax_final > INITIAL_CAPITAL:
    print(f"Effective tax rate: {after_tax_portfolio.taxes_paid / (pre_tax_final - INITIAL_CAPITAL):.1%}")
print()

# Selection distribution
selection_counts = monthly_df['Selection'].value_counts()
print("="*100)
print("SELECTION DISTRIBUTION")
print("="*100)
for selection, count in selection_counts.items():
    pct = count / len(monthly_df) * 100
    print(f"{selection:<10} {count:>4} months ({pct:>5.1f}%)")
print()

# Save results
output_dir = Path('docs/strategy_results/dual_momentum_roc12')
output_dir.mkdir(parents=True, exist_ok=True)

annual_df.to_csv(output_dir / 'annual_returns_with_taxes.csv', index=False, float_format='%.4f')
print(f"✅ Saved: {output_dir / 'annual_returns_with_taxes.csv'}")

monthly_export = monthly_df[['Selection', 'US_Above_MA', 'INTL_Above_MA', 'US_Momentum', 'INTL_Momentum',
                              'Pre_Tax_Value', 'After_Tax_Value', 'Pre_Tax_Return', 'After_Tax_Return',
                              'Tax_Paid_Cumulative']].copy()
monthly_export.to_csv(output_dir / 'monthly_returns.csv', float_format='%.6f')
print(f"✅ Saved: {output_dir / 'monthly_returns.csv'}")

summary = {
    'Strategy': 'Dual Momentum MA200 (US vs International)',
    'Period': f"{monthly_df.index[0].date()} to {monthly_df.index[-1].date()}",
    'Years': years,
    'Pre_Tax_CAGR': pre_tax_cagr,
    'After_Tax_CAGR': after_tax_cagr,
    'Tax_Drag': tax_drag,
    'Pre_Tax_Final': pre_tax_final,
    'After_Tax_Final': after_tax_final,
    'Total_Taxes': after_tax_portfolio.taxes_paid,
    'Effective_Tax_Rate': after_tax_portfolio.taxes_paid / (pre_tax_final - INITIAL_CAPITAL) if pre_tax_final > INITIAL_CAPITAL else 0,
}

summary_df = pd.DataFrame([summary])
summary_df.to_csv(output_dir / 'summary_with_taxes.csv', index=False, float_format='%.4f')
print(f"✅ Saved: {output_dir / 'summary_with_taxes.csv'}")
print()

# Save to database
save_backtest_results(
    strategy_name='dual_momentum',
    variant='roc12_ma200',
    monthly_df=monthly_df,
    annual_df=annual_df,
    metrics={
        'period_start': str(monthly_df.index[0].date()),
        'period_end': str(monthly_df.index[-1].date()),
        'years': years,
        'pre_tax_cagr': pre_tax_cagr,
        'after_tax_cagr': after_tax_cagr,
        'tax_drag': tax_drag,
        'pre_tax_final': pre_tax_final,
        'after_tax_final': after_tax_final,
        'total_taxes': after_tax_portfolio.taxes_paid,
        'effective_tax_rate': after_tax_portfolio.taxes_paid / (pre_tax_final - INITIAL_CAPITAL) if pre_tax_final > INITIAL_CAPITAL else 0,
        'num_transactions': len(after_tax_portfolio.transactions)
    },
    config={
        'universe_etfs': ['VOO', 'VEU', 'BIL'],
        'start_date': START_DATE,
        'end_date': END_DATE,
        'initial_capital': INITIAL_CAPITAL,
        'rebalance_frequency': 'monthly',
        'top_n': None,
        'description': 'Dual Momentum with 12M ROC and MA200 filter (1997-2026)'
    }
)

print("="*100)
print("DONE")
print("="*100)
