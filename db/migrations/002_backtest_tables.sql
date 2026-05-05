-- Migration 002: Add Backtest Result Tables
-- Created: 2026-05-03
-- Purpose: Store historical backtest results for GTAA 3/6 and Dual Momentum strategies

-- Backtest configurations (metadata about each backtest)
CREATE TABLE IF NOT EXISTS backtest_configs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    strategy_name TEXT NOT NULL,  -- 'gtaa6', 'gtaa3', 'dual_momentum'
    variant TEXT NOT NULL,  -- 'equal_weight', 'hold_until_replaced'
    universe_etfs TEXT,  -- JSON array of ETF symbols
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    initial_capital REAL DEFAULT 10000.0,
    rebalance_frequency TEXT,  -- 'monthly', 'on_signal_change'
    top_n INTEGER,  -- 3 or 6 for GTAA, NULL for dual momentum
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(strategy_name, variant)
);

-- Monthly backtest returns (time series data)
CREATE TABLE IF NOT EXISTS backtest_monthly_returns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    config_id INTEGER NOT NULL,
    date DATE NOT NULL,
    pre_tax_value REAL NOT NULL,
    after_tax_value REAL NOT NULL,
    pre_tax_return REAL,
    after_tax_return REAL,
    tax_paid_cumulative REAL DEFAULT 0,
    cash_weight REAL DEFAULT 0,  -- BIL allocation (0.0 to 1.0)
    holdings TEXT,  -- Comma-separated list of tickers
    num_holdings INTEGER,
    FOREIGN KEY (config_id) REFERENCES backtest_configs(id) ON DELETE CASCADE,
    UNIQUE(config_id, date)
);

-- Annual backtest summary
CREATE TABLE IF NOT EXISTS backtest_annual_returns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    config_id INTEGER NOT NULL,
    year INTEGER NOT NULL,
    pre_tax_return REAL NOT NULL,
    after_tax_return REAL NOT NULL,
    tax_drag REAL NOT NULL,
    pre_tax_end REAL NOT NULL,
    after_tax_end REAL NOT NULL,
    FOREIGN KEY (config_id) REFERENCES backtest_configs(id) ON DELETE CASCADE,
    UNIQUE(config_id, year)
);

-- Overall backtest metrics (summary statistics)
CREATE TABLE IF NOT EXISTS backtest_metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    config_id INTEGER NOT NULL UNIQUE,
    period_start DATE NOT NULL,
    period_end DATE NOT NULL,
    years REAL NOT NULL,
    pre_tax_cagr REAL NOT NULL,
    after_tax_cagr REAL NOT NULL,
    tax_drag REAL NOT NULL,
    pre_tax_final REAL NOT NULL,
    after_tax_final REAL NOT NULL,
    total_taxes REAL NOT NULL,
    effective_tax_rate REAL NOT NULL,
    max_drawdown REAL,
    max_dd_peak_date DATE,
    max_dd_trough_date DATE,
    max_dd_recovery_date DATE,
    max_dd_duration_months INTEGER,
    num_transactions INTEGER,
    FOREIGN KEY (config_id) REFERENCES backtest_configs(id) ON DELETE CASCADE
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_monthly_config_date ON backtest_monthly_returns(config_id, date DESC);
CREATE INDEX IF NOT EXISTS idx_annual_config_year ON backtest_annual_returns(config_id, year DESC);
CREATE INDEX IF NOT EXISTS idx_backtest_strategy ON backtest_configs(strategy_name, variant);
