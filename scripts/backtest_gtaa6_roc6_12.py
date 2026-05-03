"""GTAA AGG 6 with 6M/12M ROC and Treasury Yield Filter

Modified backtest using:
- Average of 6-month and 12-month ROC only (not 1, 3, 6, 12)
- Dual filter: Assets must be BOTH above 200-day MA AND beating short-term treasury yield
- Uses extended historical data with proxies back to 1998

Tracks every purchase and sale with:
- Buy date, buy price, shares purchased
- Sell date, sell price, shares sold
- Cost basis, proceeds, gains/losses
- Short-term vs long-term classification
"""

import sqlite3
import pandas as pd
from pathlib import Path
from datetime import datetime

# Tax rates
SHORT_TERM_TAX_RATE = 0.408
LONG_TERM_TAX_RATE = 0.238

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


class Portfolio:
    """Tracks portfolio holdings with detailed lot-level accounting."""

    def __init__(self, initial_cash):
        self.cash = initial_cash
        # Holdings: ticker -> list of lots [{shares, price, date, cost}, ...]
        self.holdings = {}
        # Transaction log
        self.transactions = []
        # Tax tracking
        self.annual_st_gains = []
        self.annual_lt_gains = []
        self.taxes_paid = 0
        self.carryover_loss = 0

    def get_position_value(self, ticker, price):
        """Get current market value of a position."""
        if ticker not in self.holdings:
            return 0
        total_shares = sum(lot['shares'] for lot in self.holdings[ticker])
        return total_shares * price

    def get_total_shares(self, ticker):
        """Get total shares held for a ticker."""
        if ticker not in self.holdings:
            return 0
        return sum(lot['shares'] for lot in self.holdings[ticker])

    def get_portfolio_value(self, prices):
        """Get total portfolio value (cash + holdings)."""
        value = self.cash
        for ticker, lots in self.holdings.items():
            if ticker in prices:
                total_shares = sum(lot['shares'] for lot in lots)
                value += total_shares * prices[ticker]
        return value

    def buy(self, ticker, shares, price, date):
        """Buy shares and record the lot."""
        cost = shares * price

        if cost > self.cash:
            # Can't buy more than we have cash for
            shares = self.cash / price
            cost = shares * price

        if shares < 0.0001:
            return

        self.cash -= cost

        if ticker not in self.holdings:
            self.holdings[ticker] = []

        self.holdings[ticker].append({
            'shares': shares,
            'price': price,
            'date': date,
            'cost': cost
        })

        self.transactions.append({
            'date': date,
            'type': 'BUY',
            'ticker': ticker,
            'shares': shares,
            'price': price,
            'value': cost,
            'cash_after': self.cash
        })

    def sell(self, ticker, shares_to_sell, price, date):
        """Sell shares using FIFO and track gains."""
        if ticker not in self.holdings or len(self.holdings[ticker]) == 0:
            return

        total_shares = self.get_total_shares(ticker)
        if shares_to_sell > total_shares:
            shares_to_sell = total_shares

        proceeds = 0
        remaining = shares_to_sell

        while remaining > 0.0001 and len(self.holdings[ticker]) > 0:
            lot = self.holdings[ticker][0]

            if lot['shares'] <= remaining:
                # Sell entire lot
                sale_proceeds = lot['shares'] * price
                gain = sale_proceeds - lot['cost']
                days_held = (date - lot['date']).days

                # Track for taxes
                if days_held > 365:
                    self.annual_lt_gains.append(gain)
                else:
                    self.annual_st_gains.append(gain)

                proceeds += sale_proceeds
                remaining -= lot['shares']
                self.holdings[ticker].pop(0)

            else:
                # Sell partial lot
                sale_proceeds = remaining * price
                cost_basis = (remaining / lot['shares']) * lot['cost']
                gain = sale_proceeds - cost_basis
                days_held = (date - lot['date']).days

                # Track for taxes
                if days_held > 365:
                    self.annual_lt_gains.append(gain)
                else:
                    self.annual_st_gains.append(gain)

                proceeds += sale_proceeds

                # Update lot
                lot['shares'] -= remaining
                lot['cost'] -= cost_basis
                remaining = 0

        # Clean up empty or tiny holdings
        if ticker in self.holdings:
            # Remove lots with tiny share counts
            self.holdings[ticker] = [lot for lot in self.holdings[ticker] if lot['shares'] >= 0.0001]
            # Remove ticker if no lots remain
            if len(self.holdings[ticker]) == 0:
                del self.holdings[ticker]

        self.cash += proceeds

        self.transactions.append({
            'date': date,
            'type': 'SELL',
            'ticker': ticker,
            'shares': shares_to_sell,
            'price': price,
            'value': proceeds,
            'cash_after': self.cash
        })

    def sell_all(self, ticker, price, date):
        """Sell all shares of a ticker."""
        total_shares = self.get_total_shares(ticker)
        if total_shares > 0:
            self.sell(ticker, total_shares, price, date)

    def calculate_year_end_taxes(self, prices, tax_date):
        """Calculate and pay taxes at year end.

        If not enough cash, sells positions proportionally to raise cash.
        These sales create additional taxable gains (tracked for next year).
        """
        if len(self.annual_st_gains) == 0 and len(self.annual_lt_gains) == 0:
            return 0

        st_total = sum(self.annual_st_gains)
        lt_total = sum(self.annual_lt_gains)
        st_net, lt_net = st_total, lt_total

        # Offset ST gains with LT losses and vice versa
        if st_net > 0 and lt_net < 0:
            offset = min(st_net, -lt_net)
            st_net -= offset
            lt_net += offset
        elif lt_net > 0 and st_net < 0:
            offset = min(lt_net, -st_net)
            lt_net -= offset
            st_net += offset

        # Apply carryover loss
        st_taxable = 0
        lt_taxable = 0

        if st_net > 0:
            st_taxable = max(0, st_net - self.carryover_loss)
            self.carryover_loss = max(0, self.carryover_loss - st_net)

        if lt_net > 0:
            lt_taxable = max(0, lt_net - self.carryover_loss)
            self.carryover_loss = max(0, self.carryover_loss - lt_net)

        # Accumulate losses for carryover
        if st_net < 0:
            self.carryover_loss += abs(st_net)
        if lt_net < 0:
            self.carryover_loss += abs(lt_net)

        # Calculate tax
        tax = st_taxable * SHORT_TERM_TAX_RATE + lt_taxable * LONG_TERM_TAX_RATE

        # IMPORTANT: Raise cash for taxes by selling positions if needed
        # Start new gains list for next year (these sales will be taxed next year)
        next_year_st_gains = []
        next_year_lt_gains = []

        if self.cash < tax and tax > 0:
            cash_needed = tax - self.cash

            # Sell positions proportionally to raise cash
            total_position_value = sum(self.get_position_value(ticker, prices[ticker])
                                      for ticker in self.holdings.keys()
                                      if ticker in prices)

            if total_position_value > 0:
                for ticker in list(self.holdings.keys()):
                    if ticker not in prices or cash_needed <= 0:
                        continue

                    position_value = self.get_position_value(ticker, prices[ticker])
                    fraction_to_sell = min(1.0, cash_needed / total_position_value)
                    shares_to_sell = self.get_total_shares(ticker) * fraction_to_sell

                    # Sell and track gains (for NEXT year's taxes)
                    if shares_to_sell > 0.001:
                        # Store current annual_st/lt_gains temporarily
                        saved_st = self.annual_st_gains
                        saved_lt = self.annual_lt_gains
                        self.annual_st_gains = []
                        self.annual_lt_gains = []

                        # Sell (this will add to annual_st/lt_gains)
                        self.sell(ticker, shares_to_sell, prices[ticker], tax_date)

                        # Move these gains to next year
                        next_year_st_gains.extend(self.annual_st_gains)
                        next_year_lt_gains.extend(self.annual_lt_gains)

                        # Restore this year's gains
                        self.annual_st_gains = saved_st
                        self.annual_lt_gains = saved_lt

                        cash_needed -= shares_to_sell * prices[ticker]

        # Pay tax from cash (should have enough now)
        self.cash -= tax
        self.taxes_paid += tax

        # Reset annual gains (and add next year's gains from tax payment sales)
        self.annual_st_gains = next_year_st_gains
        self.annual_lt_gains = next_year_lt_gains

        return tax


# Main backtest
START_DATE = '1998-01-01'
END_DATE = '2026-05-01'
INITIAL_CAPITAL = 10000.0
TOP_N = 6

print("="*100)
print("GTAA AGG 6 - 6M/12M ROC WITH TREASURY YIELD FILTER")
print("="*100)
print("Selection Criteria:")
print("  1. Rank by average of 6-month and 12-month ROC")
print("  2. Must be above 200-day MA")
print("  3. Must be beating short-term treasury yield")
print("="*100)
print()

# Load data (use tiingo_stocks_etfs database which has historical proxies)
conn = sqlite3.connect('/Users/patrick/Dropbox/programming/tiingo_stocks_etfs/data/strategies.db')

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
            # Detect proxy switch and calculate scaling factor
            if last_proxy is not None and proxy_ticker != last_proxy:
                # Get the last price from old proxy
                if price_data:
                    last_price = price_data[-1]['close']
                    new_proxy_price = proxy_cache[proxy_ticker][date_ts]
                    # Scale new proxy to match old proxy's price level
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

# Use ONLY 6-month and 12-month ROC average
roc_6m = monthly_prices.pct_change(6)
roc_12m = monthly_prices.pct_change(12)
avg_momentum = (roc_6m + roc_12m) / 2  # Average of 6M and 12M only

ma_200 = price_df.rolling(window=200).mean()

# Calculate T-Bill returns for yield comparison
tbill_monthly = tbill_daily.reindex(month_ends, method='ffill')
tbill_roc_6m = tbill_monthly.pct_change(6)  # 6-month treasury return

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

    # DE-DUPLICATE: Remove redundant ETFs (both by proxy and by asset class)
    # VEA and EFA are both developed international (keep VEA only)
    # VCIT, VGIT, IGOV may overlap (keep VCIT only for simplicity)

    # First, remove permanently redundant tickers
    REDUNDANT_TICKERS = [
        'EFA',   # VEA is sufficient for developed ex-US
    ]
    # Note: VCIT (corp bonds), VGIT (intermediate gov), IGOV (intl gov) are NOT redundant
    # They represent different bond risk factors: credit, interest rate, and currency
    momentum_scores_filtered = momentum_scores[~momentum_scores.index.isin(REDUNDANT_TICKERS)]

    # Then de-duplicate by proxy (for historical periods using mutual funds)
    proxy_for_date_map = {}
    for ticker in momentum_scores_filtered.index:
        proxy = get_proxy_for_date(ticker, signal_date)
        if proxy:
            if proxy not in proxy_for_date_map:
                proxy_for_date_map[proxy] = []
            proxy_for_date_map[proxy].append(ticker)

    # For each proxy, keep only the first ETF (alphabetically)
    deduplicated_tickers = []
    for proxy, etf_list in proxy_for_date_map.items():
        deduplicated_tickers.append(sorted(etf_list)[0])

    # Filter to deduplicated tickers only
    momentum_scores_dedup = momentum_scores_filtered[momentum_scores_filtered.index.isin(deduplicated_tickers)]

    # NOW rank and take top 6 from de-duplicated list
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

    # Determine target holdings (top 6 above MA200 AND beating treasury yield)
    target_holdings = set()
    tbill_6m_return = tbill_roc_6m.loc[signal_date] if signal_date in tbill_roc_6m.index else None
    asset_6m_returns = roc_6m.loc[signal_date]

    for ticker in top_6_by_momentum:
        if pd.isna(current_prices[ticker]) or pd.isna(ma_200_values[ticker]):
            continue

        # Must be above MA200
        above_ma = current_prices[ticker] > ma_200_values[ticker]

        # If treasury data is available and valid, also check if beating treasury
        asset_6m = asset_6m_returns[ticker] if ticker in asset_6m_returns.index else None
        if pd.notna(tbill_6m_return) and pd.notna(asset_6m):
            # Treasury filter is active: must beat treasury
            beats_tbill = asset_6m > tbill_6m_return
        else:
            # Treasury filter not available yet: just use MA200
            beats_tbill = True

        if above_ma and beats_tbill:
            target_holdings.add(ticker)

    # EQUAL-WEIGHT REBALANCING: Only buy/sell the DIFFERENCE to reach target weight
    # Does NOT sell everything - only adjusts positions as needed!

    # Determine target weights
    # CRITICAL: We always have 6 slots (1/6 each). If an asset is below MA200,
    # its slot goes to BIL. This prevents undiversified portfolios.
    target_weights = {ticker: 0.0 for ticker in list(all_prices.keys()) + ['BIL']}
    slot_weight = 1.0 / TOP_N  # Always 1/6, regardless of how many qualify

    for ticker in top_6_by_momentum:
        if ticker in target_holdings:
            # Above MA200: allocate this slot to the asset
            target_weights[ticker] = slot_weight
        else:
            # Below MA200: allocate this slot to BIL
            target_weights['BIL'] += slot_weight

    # Rebalance each portfolio separately
    for portfolio in [pre_tax_portfolio, after_tax_portfolio]:
        portfolio_value = portfolio.get_portfolio_value(prices_with_bil)

        # For each ticker, adjust to target weight
        for ticker in list(all_prices.keys()) + ['BIL']:
            target_value = portfolio_value * target_weights[ticker]

            if ticker == 'BIL':
                current_price = tbill_price
            else:
                if pd.isna(current_prices[ticker]):
                    continue
                current_price = current_prices[ticker]

            current_value = portfolio.get_position_value(ticker, current_price)

            # Skip if already at target (within $1)
            if abs(target_value - current_value) < 1.0:
                continue

            if target_value > current_value:
                # BUY to reach target
                buy_value = target_value - current_value
                shares = buy_value / current_price
                portfolio.buy(ticker, shares, current_price, signal_date)
            else:
                # SELL to reach target
                sell_value = current_value - target_value
                shares = sell_value / current_price
                current_shares = portfolio.get_total_shares(ticker)
                shares = min(shares, current_shares)
                if shares > 0.001:
                    portfolio.sell(ticker, shares, current_price, signal_date)

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
    if 'BIL' in after_tax_portfolio.holdings:
        bil_val = after_tax_portfolio.get_position_value('BIL', tbill_price)
        if bil_val > 1.0:
            holdings_list.append('BIL')

    bil_value = after_tax_portfolio.get_position_value('BIL', tbill_price)
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
output_dir = Path('docs/strategy_results/gtaa6_roc6_12_treasury_filter')
output_dir.mkdir(parents=True, exist_ok=True)

annual_df.to_csv(output_dir / 'annual_returns_with_taxes.csv', index=False, float_format='%.4f')
print(f"✅ Saved: {output_dir / 'annual_returns_with_taxes.csv'}")

monthly_export = monthly_df[['Pre_Tax_Value', 'After_Tax_Value', 'Pre_Tax_Return', 'After_Tax_Return',
                              'Tax_Paid_Cumulative', 'BIL_Weight', 'Holdings', 'Num_Holdings']].copy()
monthly_export.to_csv(output_dir / 'monthly_returns.csv', float_format='%.6f')
print(f"✅ Saved: {output_dir / 'monthly_returns.csv'}")

summary = {
    'Strategy': 'GTAA 6 - ROC6/12 with Treasury Filter',
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
