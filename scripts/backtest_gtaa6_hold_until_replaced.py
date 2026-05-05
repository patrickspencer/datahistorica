"""GTAA AGG 6 Hold Until Replaced - Clean Implementation with Full Lot Tracking

Tracks every purchase and sale with:
- Buy date, buy price, shares purchased
- Sell date, sell price, shares sold
- Cost basis, proceeds, gains/losses
- Short-term vs long-term classification
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

ETF_UNIVERSE = {
    'GSG': 'Commodities', 'IAU': 'Gold', 'VBK': 'Mid-cap growth', 'VWO': 'Emerging markets',
    'VBR': 'Small-cap value', 'VEA': 'Developed ex-US', 'VTV': 'Value',
    'VCIT': 'Corporate bonds', 'VGIT': 'Gov bonds', 'IGOV': 'Intl gov bonds',
    'EFA': 'International', 'QQQ': 'Nasdaq',
    'VNQ': 'Real estate', 'MTUM': 'Momentum factor', 'VGLT': 'Long-term treasury',
}

def get_proxy_for_date(etf_ticker, date_str):
    """Get the appropriate proxy ticker for a given ETF and date."""
    date = pd.to_datetime(date_str)

    if etf_ticker == 'IAU':
        if date < pd.to_datetime('2004-11-18'):
            return 'VGPMX'
        elif date < pd.to_datetime('2010-01-04'):
            return 'GLD'
        else:
            return 'IAU'
    elif etf_ticker == 'GSG':
        if date < pd.to_datetime('2002-07-01'):
            return None
        elif date < pd.to_datetime('2010-01-04'):
            return 'PCRIX'
        else:
            return 'GSG'
    elif etf_ticker == 'QQQ':
        if date < pd.to_datetime('2005-01-18'):
            return None
        else:
            return 'QQQ'
    elif etf_ticker == 'VNQ':
        if date < pd.to_datetime('2005-01-18'):
            return None  # No good proxy before VNQ launch
        else:
            return 'VNQ'
    elif etf_ticker == 'MTUM':
        # Use SPY/VFINX as proxy before MTUM launch (2013-04-16)
        if date < pd.to_datetime('1996-05-01'):
            return 'VFINX'  # S&P 500 mutual fund
        elif date < pd.to_datetime('2013-04-16'):
            return 'SPY'  # S&P 500 ETF
        else:
            return 'MTUM'  # Will be None if no data, but proxy logic is ready
    elif etf_ticker == 'VGLT':
        # Use VBMFX as rough proxy before VGLT launch (2009-11-19)
        if date < pd.to_datetime('2009-11-19'):
            return 'VBMFX'  # Total bond market
        else:
            return 'VGLT'  # Will be None if no data, but proxy logic is ready
    elif date < pd.to_datetime('2010-01-04'):
        proxies = {
            'VBK': 'VISGX', 'VBR': 'VISVX', 'VTV': 'VIVAX',
            'VWO': 'VEIEX', 'VEA': 'VGTSX', 'EFA': 'VGTSX',
            'VCIT': 'VBMFX', 'VGIT': 'VBMFX', 'IGOV': 'VBMFX',
        }
        return proxies.get(etf_ticker, etf_ticker)
    else:
        return etf_ticker


# Main backtest
START_DATE = '1998-01-01'
END_DATE = '2026-05-01'
INITIAL_CAPITAL = 10000.0
TOP_N = 6

print("="*100)
print("GTAA AGG 6 'HOLD UNTIL REPLACED' - CLEAN IMPLEMENTATION")
print("="*100)
print()

# Load data
conn = sqlite3.connect('data/strategies.db')

all_prices = {}
for etf_ticker in ETF_UNIVERSE.keys():
    price_data = []
    date_range_query = f"""
        SELECT DISTINCT p.date FROM prices p
        JOIN tickers t ON p.ticker_id = t.id
        WHERE p.date >= '{START_DATE}' AND p.date <= '{END_DATE}'
        ORDER BY p.date
    """
    all_dates = pd.read_sql_query(date_range_query, conn)['date'].tolist()
    proxy_cache = {}
    last_proxy = None
    scaling_factor = 1.0

    for date in all_dates:
        proxy_ticker = get_proxy_for_date(etf_ticker, date)
        if proxy_ticker is None:
            continue

        if proxy_ticker not in proxy_cache:
            query = f"""
                SELECT p.date, p.adj_close as close FROM prices p
                JOIN tickers t ON p.ticker_id = t.id
                WHERE t.symbol = '{proxy_ticker}'
                  AND p.date >= '{START_DATE}' AND p.date <= '{END_DATE}'
                ORDER BY p.date
            """
            df = pd.read_sql_query(query, conn)
            if len(df) > 0:
                df['date'] = pd.to_datetime(df['date'])
                df = df.set_index('date')
                proxy_cache[proxy_ticker] = df['close']
            else:
                proxy_cache[proxy_ticker] = pd.Series(dtype=float)

        date_ts = pd.to_datetime(date)
        if date_ts in proxy_cache[proxy_ticker].index:
            # Detect proxy switch and calculate scaling factor to maintain price continuity
            if last_proxy is not None and proxy_ticker != last_proxy:
                if price_data:
                    last_price = price_data[-1]['close']
                    new_proxy_price = proxy_cache[proxy_ticker][date_ts]
                    scaling_factor = last_price / new_proxy_price

            price = proxy_cache[proxy_ticker][date_ts] * scaling_factor
            price_data.append({'date': date_ts, 'close': price})
            last_proxy = proxy_ticker

    if price_data:
        df = pd.DataFrame(price_data).set_index('date')
        all_prices[etf_ticker] = df['close']

price_df = pd.DataFrame(all_prices).ffill()

# T-bill data
tbill_pre_query = f"""
    SELECT p.date, p.adj_close as close FROM prices p
    JOIN tickers t ON p.ticker_id = t.id
    WHERE t.symbol = 'VBMFX' AND p.date >= '{START_DATE}' AND p.date < '2010-01-04'
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
    WHERE t.symbol = 'BIL' AND p.date >= '2010-01-04' AND p.date <= '{END_DATE}'
    ORDER BY p.date
"""
tbill_post_df = pd.read_sql_query(tbill_post_query, conn)
if len(tbill_post_df) > 0:
    tbill_post_df['date'] = pd.to_datetime(tbill_post_df['date'])
    tbill_post_df = tbill_post_df.set_index('date')
else:
    tbill_post_df = pd.DataFrame()

conn.close()

tbill_combined = pd.concat([tbill_pre_df, tbill_post_df])
tbill_daily = tbill_combined['close'].reindex(price_df.index, method='ffill')

print(f"Loaded {len(all_prices)} assets, {len(price_df)} trading days")
print()

# Calculate signals
month_ends = price_df.resample('ME').last().index
monthly_prices = price_df.reindex(month_ends, method='ffill')

roc_1m = monthly_prices.pct_change(1)
roc_3m = monthly_prices.pct_change(3)
roc_6m = monthly_prices.pct_change(6)
roc_12m = monthly_prices.pct_change(12)
avg_momentum = (roc_1m + roc_3m + roc_6m + roc_12m) / 4
ma_200 = price_df.rolling(window=200).mean()

# Initialize portfolios
pre_tax_portfolio = Portfolio(INITIAL_CAPITAL)
after_tax_portfolio = Portfolio(INITIAL_CAPITAL)

# Track current holdings
current_holdings = set()

monthly_data = []

for i, signal_date in enumerate(month_ends):
    if i < 12:
        continue

    # Get momentum scores
    momentum_scores = avg_momentum.loc[signal_date].dropna()

    # DE-DUPLICATE: Remove redundant ETFs
    # EFA is redundant with VEA (both developed ex-US)
    REDUNDANT_TICKERS = ['EFA']
    # Note: VCIT (corp bonds), VGIT (intermediate gov), IGOV (intl gov) are NOT redundant
    # They represent different bond risk factors: credit, interest rate, and currency
    momentum_scores_filtered = momentum_scores[~momentum_scores.index.isin(REDUNDANT_TICKERS)]

    # Also de-duplicate by proxy for historical periods
    proxy_for_date_map = {}
    for ticker in momentum_scores_filtered.index:
        proxy = get_proxy_for_date(ticker, signal_date)
        if proxy:
            if proxy not in proxy_for_date_map:
                proxy_for_date_map[proxy] = []
            proxy_for_date_map[proxy].append(ticker)

    # Keep only first ETF alphabetically for each proxy
    deduplicated_tickers = []
    for proxy, etf_list in proxy_for_date_map.items():
        deduplicated_tickers.append(sorted(etf_list)[0])

    # Filter to deduplicated tickers
    momentum_scores_dedup = momentum_scores_filtered[momentum_scores_filtered.index.isin(deduplicated_tickers)]

    # Rank and take top 6 from de-duplicated list
    top_6_by_momentum = momentum_scores_dedup.sort_values(ascending=False).head(TOP_N).index.tolist()

    # Trading date
    if signal_date not in price_df.index:
        trading_date = price_df.index[price_df.index <= signal_date][-1]
    else:
        trading_date = signal_date

    current_prices = price_df.loc[trading_date]
    ma_200_values = ma_200.loc[trading_date]
    tbill_price = tbill_daily.loc[trading_date]

    # Add BIL to prices
    prices_with_bil = current_prices.to_dict()
    prices_with_bil['BIL'] = tbill_price

    # Determine target holdings (top 6 above MA200)
    target_holdings = set()
    for ticker in top_6_by_momentum:
        if pd.isna(current_prices[ticker]) or pd.isna(ma_200_values[ticker]):
            continue
        if current_prices[ticker] > ma_200_values[ticker]:
            target_holdings.add(ticker)

    # Determine what to sell and buy
    to_sell = current_holdings - target_holdings
    to_buy = target_holdings - current_holdings

    # Calculate how many slots should be in BIL (non-qualifying top 6)
    num_bil_slots = TOP_N - len(target_holdings)

    # SELL positions that dropped out (both portfolios)
    for ticker in to_sell:
        pre_tax_portfolio.sell_all(ticker, current_prices[ticker], signal_date)
        after_tax_portfolio.sell_all(ticker, current_prices[ticker], signal_date)

    # If buying new positions, sell BIL to free up cash
    if len(to_buy) > 0:
        pre_tax_portfolio.sell_all('BIL', tbill_price, signal_date)
        after_tax_portfolio.sell_all('BIL', tbill_price, signal_date)

    # BUY new positions using 1/6 slot sizing
    if len(to_buy) > 0:
        # Calculate total portfolio value
        pre_tax_total = pre_tax_portfolio.get_portfolio_value(prices_with_bil)
        after_tax_total = after_tax_portfolio.get_portfolio_value(prices_with_bil)

        # Each new position gets 1/6 of portfolio value
        pre_tax_slot = pre_tax_total / TOP_N
        after_tax_slot = after_tax_total / TOP_N

        # Pre-tax
        for ticker in to_buy:
            shares = pre_tax_slot / current_prices[ticker]
            pre_tax_portfolio.buy(ticker, shares, current_prices[ticker], signal_date)

        # After-tax
        for ticker in to_buy:
            shares = after_tax_slot / current_prices[ticker]
            after_tax_portfolio.buy(ticker, shares, current_prices[ticker], signal_date)

    # Update current holdings
    current_holdings = target_holdings.copy()

    # Invest remaining cash in BIL (representing non-qualifying slots)
    if pre_tax_portfolio.cash > 1.0:
        shares = pre_tax_portfolio.cash / tbill_price
        pre_tax_portfolio.buy('BIL', shares, tbill_price, signal_date)

    if after_tax_portfolio.cash > 1.0:
        shares = after_tax_portfolio.cash / tbill_price
        after_tax_portfolio.buy('BIL', shares, tbill_price, signal_date)

    # Year-end taxes
    year_end = signal_date.month == 12 or i == len(month_ends) - 1
    if year_end:
        after_tax_portfolio.calculate_year_end_taxes(prices_with_bil, signal_date)

    # Calculate portfolio values
    pre_tax_value = pre_tax_portfolio.get_portfolio_value(prices_with_bil)
    after_tax_value = after_tax_portfolio.get_portfolio_value(prices_with_bil)

    # Track holdings (only count positions worth > $1)
    holdings_list = []
    for ticker in after_tax_portfolio.holdings.keys():
        if ticker == 'BIL':
            continue
        price = prices_with_bil.get(ticker, 0)
        value = after_tax_portfolio.get_position_value(ticker, price)
        if value > 1.0:
            holdings_list.append(ticker)

    # Add BIL if it has meaningful value
    bil_value = after_tax_portfolio.get_position_value('BIL', tbill_price)
    if 'BIL' in after_tax_portfolio.holdings and bil_value > 1.0:
        holdings_list.append('BIL')

    bil_weight = bil_value / after_tax_value if after_tax_value > 0 else 0

    monthly_data.append({
        'Date': signal_date,
        'Pre_Tax_Value': pre_tax_value,
        'After_Tax_Value': after_tax_value,
        'Tax_Paid_Cumulative': after_tax_portfolio.taxes_paid,
        'BIL_Weight': bil_weight,
        'Holdings': ','.join(holdings_list),
        'Num_Holdings': len(holdings_list),
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

# Save results
output_dir = Path('docs/strategy_results/gtaa6_hold_until_replaced')
output_dir.mkdir(parents=True, exist_ok=True)

annual_df.to_csv(output_dir / 'annual_returns_with_taxes.csv', index=False, float_format='%.4f')
print(f"✅ Saved: {output_dir / 'annual_returns_with_taxes.csv'}")

monthly_export = monthly_df[['Pre_Tax_Value', 'After_Tax_Value', 'Pre_Tax_Return', 'After_Tax_Return',
                              'Tax_Paid_Cumulative', 'BIL_Weight', 'Holdings', 'Num_Holdings']].copy()
monthly_export.to_csv(output_dir / 'monthly_returns.csv', float_format='%.6f')
print(f"✅ Saved: {output_dir / 'monthly_returns.csv'}")

summary = {
    'Strategy': 'GTAA AGG 6 Hold Until Replaced (1998-2026)',
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
    strategy_name='gtaa6',
    variant='hold_until_replaced',
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
        'universe_etfs': list(ETF_UNIVERSE.keys()),
        'start_date': START_DATE,
        'end_date': END_DATE,
        'initial_capital': INITIAL_CAPITAL,
        'rebalance_frequency': 'on_signal_change',
        'top_n': TOP_N,
        'description': 'GTAA 6 Hold Until Replaced - only rebalance when signals change (1998-2026)'
    }
)

# Print summary statistics
print("="*100)
print("PORTFOLIO STATISTICS")
print("="*100)
print()
print(f"Pre-tax transactions: {len(pre_tax_portfolio.transactions)}")
print(f"After-tax transactions: {len(after_tax_portfolio.transactions)}")
print(f"After-tax cash remaining: ${after_tax_portfolio.cash:,.2f}")
print(f"Carryover loss: ${after_tax_portfolio.carryover_loss:,.2f}")
print()
