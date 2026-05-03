"""Tiingo API Client

Simple client for fetching price data from Tiingo.
Adapted from tiingo_stocks_etfs package.
"""

import requests
from datetime import datetime, timedelta
from typing import List, Dict, Optional


class TiingoClient:
    """Client for Tiingo API."""

    def __init__(self, api_key: str, base_url: str = "https://api.tiingo.com"):
        self.api_key = api_key
        self.base_url = base_url
        self.session = requests.Session()
        self.session.headers.update({
            "Content-Type": "application/json",
            "Authorization": f"Token {api_key}"
        })

    def get_daily_prices(
        self,
        ticker: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> List[Dict]:
        """Fetch daily OHLCV data for a ticker.

        Args:
            ticker: Stock/ETF symbol
            start_date: Start date (YYYY-MM-DD), defaults to 400 days ago
            end_date: End date (YYYY-MM-DD), defaults to today

        Returns:
            List of daily price dictionaries
        """
        if not end_date:
            end_date = datetime.now().strftime("%Y-%m-%d")

        if not start_date:
            # Default to 400 days for MA200 calculation
            start = datetime.now() - timedelta(days=400)
            start_date = start.strftime("%Y-%m-%d")

        url = f"{self.base_url}/tiingo/daily/{ticker}/prices"
        params = {
            "startDate": start_date,
            "endDate": end_date,
            "format": "json"
        }

        try:
            response = self.session.get(url, params=params)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"Error fetching {ticker}: {e}")
            return []

    def get_latest_price(self, ticker: str) -> Optional[Dict]:
        """Fetch most recent price for a ticker."""
        prices = self.get_daily_prices(ticker)
        if prices:
            return prices[-1]
        return None
