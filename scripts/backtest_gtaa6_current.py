"""GTAA AGG 6 Backtest with Current Universe

Backtests GTAA 6 strategy using the current 14-asset universe:
- MTUM, VBK, VBR, VTV, VEA, VWO, VNQ, QQQ, GSG, IAU, VCIT, VGIT, VGLT, IGOV

Strategy Rules:
- Monthly rebalancing (last trading day of month)
- Rank all assets by average momentum (1M, 3M, 6M, 12M ROC)
- Select top 6 assets that are above their 200-day MA
- Equal weight allocation (1/6 each)
- Assets below MA200 have their slot go to cash (BIL)
"""

import sqlite3
import pandas as pd
from pathlib import Path
from datetime import datetime

# Tax rates
SHORT_TERM_TAX_RATE = 0.408
LONG_TERM_TAX_RATE = 0.238

# Current ETF universe (14 assets)
ETF_UNIVERSE = {
    'MTUM': 'US Momentum Factor',
    'VBK': 'US Small Cap Growth',
    'VBR': 'US Small Cap Value',
    'VTV': 'US Large Cap Value',
    'VEA': 'Developed Markets (ex-US)',
    'VWO': 'Emerging Markets',
    'VNQ': 'US Real Estate',
    'QQQ': 'US Tech (Nasdaq)',
    'GSG': 'Commodities',
    'IAU': 'Gold',
    'VCIT': 'Corporate Bonds (Intermediate)',
    'VGIT': 'Government Bonds (Intermediate)',
    'VGLT': 'Government Bonds (Long-Term)',
    'IGOV': 'International Government Bonds',
}


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

        # Clean up empty holdings
        if ticker in self.holdings:
            self.holdings[ticker] = [lot for lot in self.holdings[ticker] if lot['shares'] >= 0.0001]
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

    def calculate_year_end_taxes(self, prices, tax_date):
        """Calculate and pay taxes at year end."""
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

        # Raise cash for taxes if needed
        next_year_st_gains = []
        next_year_lt_gains = []

        if self.cash < tax and tax > 0:
            cash_needed = tax - self.cash

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

                    if shares_to_sell > 0.001:
                        saved_st = self.annual_st_gains
                        saved_lt = self.annual_lt_gains
                        self.annual_st_gains = []
                        self.annual_lt_gains = []

                        self.sell(ticker, shares_to_sell, prices[ticker], tax_date)

                        next_year_st_gains.extend(self.annual_st_gains)
                        next_year_lt_gains.extend(self.annual_lt_gains)

                        self.annual_st_gains = saved_st
                        self.annual_lt_gains = saved_lt

                        cash_needed -= shares_to_sell * prices[ticker]

        # Pay tax
        self.cash -= tax
        self.taxes_paid += tax

        # Reset annual gains
        self.annual_st_gains = next_year_st_gains
        self.annual_lt_gains = next_year_lt_gains

        return tax


# Main backtest parameters
START_DATE = '2013-05-01'  # Start when all current ETFs have data (MTUM launched 2013-04-16)
END_DATE = '2026-05-01'
INITIAL_CAPITAL = 10000.0
TOP_N = 6

print("="*100)
print("GTAA AGG 6 BACKTEST - CURRENT UNIVERSE")
print("="*100)
print()
print(f"Universe: {len(ETF_UNIVERSE)} assets")
for ticker, desc in sorted(ETF_UNIVERSE.items()):
    print(f"  {ticker}: {desc}")
print()

# Load data from strategy-tracker database
db_path = Path(__file__).parent.parent / 'data' / 'strategies.db'
conn = sqlite3.connect(str(db_path))

# Load price data for all assets
all_prices = {}
for etf_ticker in ETF_UNIVERSE.keys():
    query = f"""
        SELECT p.date, p.adj_close as close
        FROM prices p
        JOIN tickers t ON p.ticker_id = t.id
        WHERE t.symbol = '{etf_ticker}'
          AND p.date >= '{START_DATE}'
          AND p.date <= '{END_DATE}'
        ORDER BY p.date
    """
    df = pd.read_sql_query(query, conn)
    if len(df) > 0:
        df['date'] = pd.to_datetime(df['date'])
        df = df.set_index('date')
        all_prices[etf_ticker] = df['close']

# Load BIL (cash) data
bil_query = f"""
    SELECT p.date, p.adj_close as close
    FROM prices p
    JOIN tickers t ON p.ticker_id = t.id
    WHERE t.symbol = 'BIL'
      AND p.date >= '{START_DATE}'
      AND p.date <= '{END_DATE}'
    ORDER BY p.date
"""
bil_df = pd.read_sql_query(bil_query, conn)
conn.close()

if len(bil_df) > 0:
    bil_df['date'] = pd.to_datetime(bil_df['date'])
    bil_df = bil_df.set_index('date')
    bil_daily = bil_df['close']
else:
    print("ERROR: No BIL data found!")
    exit(1)

# Create price dataframe and handle NaN values
price_df = pd.DataFrame(all_prices).ffill()

bil_daily = bil_daily.reindex(price_df.index, method='ffill')

print(f"Loaded {len(all_prices)} assets, {len(price_df)} trading days ({price_df.index[0].date()} to {price_df.index[-1].date()})")
print()

# Calculate signals
month_ends = price_df.resample('ME').last().index
monthly_prices = price_df.reindex(month_ends, method='ffill')

# Calculate ROC momentum scores
roc_1m = monthly_prices.pct_change(1)
roc_3m = monthly_prices.pct_change(3)
roc_6m = monthly_prices.pct_change(6)
roc_12m = monthly_prices.pct_change(12)
avg_momentum = (roc_1m + roc_3m + roc_6m + roc_12m) / 4

# Calculate 200-day MA
ma_200 = price_df.rolling(window=200).mean()

# Initialize portfolios
pre_tax_portfolio = Portfolio(INITIAL_CAPITAL)
after_tax_portfolio = Portfolio(INITIAL_CAPITAL)

monthly_data = []

for i, signal_date in enumerate(month_ends):
    if i < 12:  # Need 12 months of history for ROC
        continue

    # Get momentum scores for all assets
    momentum_scores = avg_momentum.loc[signal_date].dropna()

    # Rank and take top 6
    top_6_by_momentum = momentum_scores.sort_values(ascending=False).head(TOP_N).index.tolist()

    # Trading date
    if signal_date not in price_df.index:
        trading_date = price_df.index[price_df.index <= signal_date][-1]
    else:
        trading_date = signal_date

    current_prices = price_df.loc[trading_date]
    ma_200_values = ma_200.loc[trading_date]
    bil_price = bil_daily.loc[trading_date]

    # Add BIL to prices
    prices_with_bil = current_prices.to_dict()
    prices_with_bil['BIL'] = bil_price

    # Determine target holdings (top 6 above MA200)
    target_holdings = set()
    for ticker in top_6_by_momentum:
        if pd.isna(current_prices[ticker]) or pd.isna(ma_200_values[ticker]):
            continue
        if current_prices[ticker] > ma_200_values[ticker]:
            target_holdings.add(ticker)

    # Determine target weights (always 6 slots of 1/6 each)
    target_weights = {ticker: 0.0 for ticker in list(all_prices.keys()) + ['BIL']}
    slot_weight = 1.0 / TOP_N

    for ticker in top_6_by_momentum:
        if ticker in target_holdings:
            # Above MA200: allocate slot to asset
            target_weights[ticker] = slot_weight
        else:
            # Below MA200: allocate slot to cash (BIL)
            target_weights['BIL'] += slot_weight

    # Rebalance each portfolio
    for portfolio in [pre_tax_portfolio, after_tax_portfolio]:
        portfolio_value = portfolio.get_portfolio_value(prices_with_bil)

        # Adjust each position to target weight
        for ticker in list(all_prices.keys()) + ['BIL']:
            target_value = portfolio_value * target_weights[ticker]

            if ticker == 'BIL':
                current_price = bil_price
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

    # Track holdings
    holdings_list = []
    for ticker in after_tax_portfolio.holdings.keys():
        price = prices_with_bil.get(ticker, 0)
        value = after_tax_portfolio.get_position_value(ticker, price)
        if value > 1.0:
            holdings_list.append(ticker)

    bil_value = after_tax_portfolio.get_position_value('BIL', bil_price)
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

# Calculate max drawdown
pre_tax_cummax = monthly_df['Pre_Tax_Value'].cummax()
pre_tax_drawdown = (monthly_df['Pre_Tax_Value'] - pre_tax_cummax) / pre_tax_cummax
max_dd = pre_tax_drawdown.min()
max_dd_date = pre_tax_drawdown.idxmin()
peak_date = pre_tax_cummax[:max_dd_date].idxmax()

# Find recovery date
recovery_date = None
if max_dd_date in monthly_df.index:
    peak_value = pre_tax_cummax[peak_date]
    future_dates = monthly_df.index[monthly_df.index > max_dd_date]
    for date in future_dates:
        if monthly_df.loc[date, 'Pre_Tax_Value'] >= peak_value:
            recovery_date = date
            break

dd_duration_months = None
if recovery_date:
    dd_duration_months = (recovery_date.year - peak_date.year) * 12 + (recovery_date.month - peak_date.month)

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
print(f"{'Max Drawdown':<30} {max_dd:>18.1%}")
print()
print(f"Total taxes paid: ${after_tax_portfolio.taxes_paid:,.2f}")
if pre_tax_final > INITIAL_CAPITAL:
    print(f"Effective tax rate: {after_tax_portfolio.taxes_paid / (pre_tax_final - INITIAL_CAPITAL):.1%}")
print()

# Save results
output_dir = Path('docs/strategy_results/gtaa6_current')
output_dir.mkdir(parents=True, exist_ok=True)

annual_df.to_csv(output_dir / 'annual_returns_with_taxes.csv', index=False, float_format='%.4f')
print(f"✅ Saved: {output_dir / 'annual_returns_with_taxes.csv'}")

monthly_export = monthly_df[['Pre_Tax_Value', 'After_Tax_Value', 'Pre_Tax_Return', 'After_Tax_Return',
                              'Tax_Paid_Cumulative', 'BIL_Weight', 'Holdings', 'Num_Holdings']].copy()
monthly_export.to_csv(output_dir / 'monthly_returns.csv', float_format='%.6f')
print(f"✅ Saved: {output_dir / 'monthly_returns.csv'}")

# Drawdown analysis
drawdown_df = pd.DataFrame({
    'Max_Drawdown': [max_dd],
    'Peak_Date': [peak_date],
    'Trough_Date': [max_dd_date],
    'Recovery_Date': [recovery_date],
    'Duration_Months': [dd_duration_months]
})
drawdown_df.to_csv(output_dir / 'drawdown_analysis.csv', index=False)
print(f"✅ Saved: {output_dir / 'drawdown_analysis.csv'}")

summary = {
    'Strategy': 'GTAA AGG 6 - Current Universe',
    'Period': f"{monthly_df.index[0].date()} to {monthly_df.index[-1].date()}",
    'Years': years,
    'Pre_Tax_CAGR': pre_tax_cagr,
    'After_Tax_CAGR': after_tax_cagr,
    'Tax_Drag': tax_drag,
    'Pre_Tax_Final': pre_tax_final,
    'After_Tax_Final': after_tax_final,
    'Total_Taxes': after_tax_portfolio.taxes_paid,
    'Effective_Tax_Rate': after_tax_portfolio.taxes_paid / (pre_tax_final - INITIAL_CAPITAL) if pre_tax_final > INITIAL_CAPITAL else 0,
    'Max_Drawdown': max_dd,
    'Max_DD_Peak_Date': peak_date,
    'Max_DD_Trough_Date': max_dd_date,
    'Max_DD_Recovery_Date': recovery_date,
    'Max_DD_Duration_Months': dd_duration_months,
}

summary_df = pd.DataFrame([summary])
summary_df.to_csv(output_dir / 'summary_with_taxes.csv', index=False, float_format='%.4f')
print(f"✅ Saved: {output_dir / 'summary_with_taxes.csv'}")
print()

print("="*100)
print("✅ BACKTEST COMPLETE!")
print("="*100)
