-- Strategy Tracker Database Schema

-- Drop existing tables
DROP TABLE IF EXISTS holdings;
DROP TABLE IF EXISTS strategy_signals;
DROP TABLE IF EXISTS strategy_universes;
DROP TABLE IF EXISTS indicators;
DROP TABLE IF EXISTS prices;
DROP TABLE IF EXISTS tickers;

-- Tickers table
CREATE TABLE tickers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT UNIQUE NOT NULL,
    name TEXT,
    asset_class TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Price history (keep rolling 400-day window for MA200 calculation)
CREATE TABLE prices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker_id INTEGER NOT NULL,
    date DATE NOT NULL,
    open REAL,
    high REAL,
    low REAL,
    close REAL NOT NULL,
    volume INTEGER,
    adj_close REAL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (ticker_id) REFERENCES tickers(id) ON DELETE CASCADE,
    UNIQUE(ticker_id, date)
);

-- Calculated indicators
CREATE TABLE indicators (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker_id INTEGER NOT NULL,
    date DATE NOT NULL,
    ma_200 REAL,
    roc_1m REAL,
    roc_3m REAL,
    roc_6m REAL,
    roc_12m REAL,
    avg_roc REAL,  -- (1m + 3m + 6m + 12m) / 4
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (ticker_id) REFERENCES tickers(id) ON DELETE CASCADE,
    UNIQUE(ticker_id, date)
);

-- Strategy signals (one row per strategy per rebalance date)
CREATE TABLE strategy_signals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    strategy_name TEXT NOT NULL,  -- 'gtaa6', 'gtaa3', 'dual_momentum'
    signal_date DATE NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(strategy_name, signal_date)
);

-- Holdings per strategy signal
CREATE TABLE holdings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    signal_id INTEGER NOT NULL,
    ticker_id INTEGER NOT NULL,
    allocation REAL NOT NULL,  -- 0.0 to 1.0 (e.g., 0.1667 for 16.67%)
    is_cash BOOLEAN DEFAULT FALSE,
    reason TEXT,  -- 'above_ma200', 'best_momentum', 'defensive', 'positive_roc', etc.
    price REAL,
    ma_200 REAL,
    momentum_score REAL,
    FOREIGN KEY (signal_id) REFERENCES strategy_signals(id) ON DELETE CASCADE,
    FOREIGN KEY (ticker_id) REFERENCES tickers(id) ON DELETE CASCADE
);

-- Strategy universe definitions
CREATE TABLE strategy_universes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    strategy_name TEXT NOT NULL,
    ticker_id INTEGER NOT NULL,
    FOREIGN KEY (ticker_id) REFERENCES tickers(id) ON DELETE CASCADE,
    UNIQUE(strategy_name, ticker_id)
);

-- Indexes for performance
CREATE INDEX idx_prices_ticker_date ON prices(ticker_id, date DESC);
CREATE INDEX idx_indicators_ticker_date ON indicators(ticker_id, date DESC);
CREATE INDEX idx_signals_strategy_date ON strategy_signals(strategy_name, signal_date DESC);
CREATE INDEX idx_holdings_signal ON holdings(signal_id);
CREATE INDEX idx_universe_strategy ON strategy_universes(strategy_name);
