"""
Portfolio Class for Backtesting with Lot-Level Tracking

Tracks portfolio holdings with detailed lot-level accounting including:
- FIFO (First In, First Out) lot accounting
- Short-term vs long-term capital gains classification
- Tax loss carryover across years
- Automatic tax payment with position liquidation if needed

Used by all backtest scripts in strategy-tracker.
"""

# Tax rates (2024)
SHORT_TERM_TAX_RATE = 0.408  # 40.8% (ordinary income + state + ACA)
LONG_TERM_TAX_RATE = 0.238   # 23.8% (15% federal + 3.8% ACA + 5% state)


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
