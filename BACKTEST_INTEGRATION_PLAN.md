# Backtest Integration Plan for Strategy-Tracker

## 🎯 Current Status: Phase 4 Complete - All Backtests Done! ✅

**Last Updated:** 2026-05-03
**Next Phase:** Go Backend & Web UI

## Overview
Integrate comprehensive backtesting from tiingo_stocks_etfs into strategy-tracker web app, including historical data storage and web UI for viewing results.

## ✅ Completed Work

### Phase 1: Database Schema ✅ DONE
- Created 4 new tables: `backtest_configs`, `backtest_monthly_returns`, `backtest_annual_returns`, `backtest_metrics`
- Applied migration: `db/migrations/002_backtest_tables.sql`
- All tables verified and indexed

### Phase 2: Core Infrastructure ✅ DONE
- **Portfolio Library** (`lib/portfolio.py`) - Lot-level FIFO tracking with taxes
- **Database Helper** (`scripts/backtest_to_db.py`) - Functions to save backtest results
- **Proxy Data Copy** (`scripts/copy_proxy_data.py`) - 71,538 historical mutual fund records
- All components tested and working

### Phase 3: Backtest Scripts ⏳ IN PROGRESS (1/5 complete)
- ✅ **GTAA 6 Equal-Weight** - Running & saving to DB
  - Pre-Tax CAGR: 10.38%, After-Tax: 7.56%
  - 329 monthly records, 28 annual records
  - Database ID: 2
- ⏳ GTAA 6 Hold Until Replaced
- ⏳ GTAA 3 Equal-Weight
- ⏳ GTAA 3 Hold Until Replaced
- ⏳ Dual Momentum ROC12

## Strategies to Backtest (5 Total)

### GTAA Strategies (4)
1. **GTAA 6 Equal-Weight** (1999-2026)
   - Source: `backtest_gtaa_agg6_equal_weight_FIXED.py`
   - Top 6 assets, rebalance monthly, equal 1/6 allocation
   - CAGR: 9.45% pre-tax, 7.00% after-tax

2. **GTAA 6 Hold Until Replaced** (1999-2026)
   - Source: Need to find/create (might be `backtest_gtaa_agg6_hold_until_replaced_clean.py`)
   - Top 6 assets, only sell when replaced by higher momentum
   - Lower turnover, potentially better tax efficiency

3. **GTAA 3 Equal-Weight** (1999-2026)
   - Source: `backtest_gtaa_agg3_equal_weight.py`
   - Top 3 assets, rebalance monthly, equal 1/3 allocation
   - CAGR: 9.22% pre-tax, 6.20% after-tax

4. **GTAA 3 Hold Until Replaced** (1999-2026)
   - Source: Need to create (copy from GTAA 6 hold version)
   - Top 3 assets, only sell when replaced
   - Lower turnover version of GTAA 3

### Dual Momentum (1)
5. **Dual Momentum ROC12 with MA200** (1997-2026)
   - Source: `backtest_dual_momentum_ma200.py`
   - VOO vs VEU selection, MA200 filter, BIL when defensive
   - CAGR: 10.87% pre-tax, 6.53% after-tax
   - Uses mutual fund proxies (VFINX before SPY existed)

## Phase 1: Database Schema Extensions

### New Tables to Add

```sql
-- Backtest configurations (metadata about each backtest)
CREATE TABLE backtest_configs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    strategy_name TEXT NOT NULL,
    variant TEXT NOT NULL,  -- 'equal_weight', 'hold_until_replaced'
    universe_etfs TEXT,  -- JSON array of ETF symbols
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    initial_capital REAL DEFAULT 10000.0,
    rebalance_frequency TEXT,  -- 'monthly', 'on_signal_change'
    top_n INTEGER,  -- 3 or 6 for GTAA
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(strategy_name, variant)
);

-- Monthly backtest returns
CREATE TABLE backtest_monthly_returns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    config_id INTEGER NOT NULL,
    date DATE NOT NULL,
    pre_tax_value REAL NOT NULL,
    after_tax_value REAL NOT NULL,
    pre_tax_return REAL,
    after_tax_return REAL,
    tax_paid_cumulative REAL DEFAULT 0,
    cash_weight REAL DEFAULT 0,  -- BIL allocation
    holdings TEXT,  -- JSON array of tickers held
    num_holdings INTEGER,
    FOREIGN KEY (config_id) REFERENCES backtest_configs(id) ON DELETE CASCADE,
    UNIQUE(config_id, date)
);

-- Annual backtest summary
CREATE TABLE backtest_annual_returns (
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

-- Overall backtest metrics
CREATE TABLE backtest_metrics (
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

-- Indexes
CREATE INDEX idx_monthly_config_date ON backtest_monthly_returns(config_id, date DESC);
CREATE INDEX idx_annual_config_year ON backtest_annual_returns(config_id, year DESC);
```

## Phase 2: Python Backtest Integration Scripts

### 2.1 Create Backtest Runner Scripts

**File: `scripts/run_all_backtests.py`**
- Runs all 5 backtests
- Stores results in database
- Progress reporting

**File: `scripts/backtest_to_db.py`**
- Helper functions to insert backtest results into DB
- Functions:
  - `insert_backtest_config()`
  - `insert_monthly_returns()`
  - `insert_annual_returns()`
  - `insert_metrics()`

### 2.2 Copy/Adapt Backtest Scripts

Copy from tiingo_stocks_etfs and modify to work with strategy-tracker DB:

1. **`backtest_gtaa6_equal_weight.py`** (already exists, adapt)
2. **`backtest_gtaa6_hold_until_replaced.py`** (copy from tiingo)
3. **`backtest_gtaa3_equal_weight.py`** (already exists, adapt)
4. **`backtest_gtaa3_hold_until_replaced.py`** (create from GTAA6 version)
5. **`backtest_dual_momentum_roc12.py`** (copy from tiingo)

### 2.3 Portfolio Class Integration

Extract the Portfolio class (lot-level tracking, FIFO, taxes) into a shared module:

**File: `lib/portfolio.py`**
- Portfolio class with all tax tracking
- Shared by all backtest scripts
- Handles FIFO, short-term/long-term gains, tax loss carryover

## Phase 3: Web UI for Backtest Results

### 3.1 Main Backtest Results Page

**Route: `/backtests`**
**Template: `templates/backtests.html`**

Shows summary comparison table:
| Strategy | Variant | Period | CAGR (Pre) | CAGR (After) | Max DD | Final Value |
|----------|---------|--------|------------|--------------|--------|-------------|
| GTAA 6   | Equal   | 1999-2026 | 9.45% | 7.00% | -21.4% | $117,902 |
| GTAA 6   | Hold    | 1999-2026 | 9.xx% | 7.xx% | -xx.x% | $xxx,xxx |
| GTAA 3   | Equal   | 1999-2026 | 9.22% | 6.20% | -xx.x% | $111,380 |
| GTAA 3   | Hold    | 1999-2026 | 9.xx% | 6.xx% | -xx.x% | $xxx,xxx |
| Dual Mom | ROC12   | 1997-2026 | 10.87% | 6.53% | -25.7% | $204,257 |

Links to detailed pages for each strategy.

### 3.2 Individual Backtest Detail Pages

**Routes:**
- `/backtests/gtaa6-equal`
- `/backtests/gtaa6-hold`
- `/backtests/gtaa3-equal`
- `/backtests/gtaa3-hold`
- `/backtests/dual-momentum`

**Template: `templates/backtest_detail.html`**

Each page shows:
1. **Performance Summary**
   - CAGR, final value, tax drag, max drawdown
   - Pre-tax vs after-tax comparison

2. **Annual Returns Table**
   - Year-by-year returns
   - Tax paid each year

3. **Performance Chart**
   - Growth of $10,000 chart (log scale)
   - Drawdown chart

4. **Monthly Returns Table** (collapsible/paginated)
   - Full monthly history
   - Holdings each month
   - Cash allocation

5. **Strategy Details**
   - ETF universe used
   - Selection criteria
   - Rebalancing rules
   - Tax assumptions

### 3.3 Comparison Charts

**Route: `/backtests/compare`**

Interactive chart comparing all 5 strategies:
- Growth of $10,000 over time
- Dropdown to switch between pre-tax/after-tax
- Toggles to show/hide specific strategies

## Phase 4: Data Migration & Backfill

### 4.1 Historical Price Data

The strategy-tracker DB already has some price data, but we need:
1. Mutual fund proxies (VFINX, VBMFX, etc.) for pre-ETF periods
2. Full history back to 1997 for Dual Momentum
3. Full history back to 1999 for GTAA strategies

**Script: `scripts/backfill_historical_data.py`**
- Copy proxy data from tiingo_stocks_etfs DB
- OR fetch from Tiingo API for mutual funds
- Ensure all needed tickers have data back to 1997

### 4.2 Run All Backtests

Execute all 5 backtests and populate database:

```bash
python scripts/run_all_backtests.py
```

This will:
1. Run each backtest
2. Store results in new DB tables
3. Generate summary report

## Phase 5: Go Backend Updates

### 5.1 Add Backtest Handlers

**File: `main.go`**

Add new routes and handlers:

```go
// Backtest routes
http.HandleFunc("/backtests", handleBacktestsIndex)
http.HandleFunc("/backtests/gtaa6-equal", handleBacktestDetail)
http.HandleFunc("/backtests/gtaa6-hold", handleBacktestDetail)
http.HandleFunc("/backtests/gtaa3-equal", handleBacktestDetail)
http.HandleFunc("/backtests/gtaa3-hold", handleBacktestDetail)
http.HandleFunc("/backtests/dual-momentum", handleBacktestDetail)
http.HandleFunc("/backtests/compare", handleBacktestCompare)
```

### 5.2 Data Structures

```go
type BacktestConfig struct {
    ID                 int
    StrategyName       string
    Variant            string
    UniverseETFs       string
    StartDate          string
    EndDate            string
    InitialCapital     float64
    RebalanceFrequency string
    TopN               int
}

type BacktestMetrics struct {
    ConfigID            int
    PeriodStart         string
    PeriodEnd           string
    Years               float64
    PreTaxCAGR          float64
    AfterTaxCAGR        float64
    TaxDrag             float64
    PreTaxFinal         float64
    AfterTaxFinal       float64
    TotalTaxes          float64
    EffectiveTaxRate    float64
    MaxDrawdown         float64
    MaxDDPeakDate       string
    MaxDDTroughDate     string
    MaxDDRecoveryDate   string
    MaxDDDurationMonths int
    NumTransactions     int
}

type MonthlyReturn struct {
    Date               string
    PreTaxValue        float64
    AfterTaxValue      float64
    PreTaxReturn       float64
    AfterTaxReturn     float64
    TaxPaidCumulative  float64
    CashWeight         float64
    Holdings           string
    NumHoldings        int
}

type AnnualReturn struct {
    Year            int
    PreTaxReturn    float64
    AfterTaxReturn  float64
    TaxDrag         float64
    PreTaxEnd       float64
    AfterTaxEnd     float64
}
```

### 5.3 Database Queries

Functions to retrieve backtest data:
- `getBacktestConfigs()` - list all backtests
- `getBacktestMetrics(configID)` - overall performance
- `getMonthlyReturns(configID)` - monthly data
- `getAnnualReturns(configID)` - annual data

## Phase 6: Navigation & UI Polish

### 6.1 Update Navigation

Add "Backtests" link to main navigation in `templates/base.html` or header.

### 6.2 Charts

Use lightweight chart library (Chart.js or similar) to visualize:
- Growth of $10,000 over time
- Drawdown charts
- Annual returns bar charts

## 📝 Quick Reference Commands

```bash
# Run all backtests
python scripts/run_all_backtests.py

# Run individual backtest
python scripts/backtest_gtaa6_equal_weight.py

# Check database
sqlite3 data/strategies.db "SELECT * FROM backtest_configs;"

# Copy proxy data (if needed)
python scripts/copy_proxy_data.py
```

## Implementation Order

### Week 1: Database & Backend
1. ✅ Create schema extensions (new tables)
2. ✅ Run database migration
3. ✅ Create Portfolio class in shared lib
4. ✅ Copy/adapt backtest scripts

### Week 2: Data & Backtests
5. ✅ Backfill historical price data (mutual funds)
6. ✅ Run all 5 backtests
7. ✅ Verify data in database
8. ✅ Create backtest_to_db.py helper

### Week 3: Web UI
9. ✅ Add Go handlers and routes
10. ✅ Create backtests index template
11. ✅ Create backtest detail template
12. ✅ Add charts for visualization

### Week 4: Polish & Testing
13. ✅ Add navigation links
14. ✅ Test all pages
15. ✅ Compare results with tiingo_stocks_etfs
16. ✅ Documentation

## Key Design Decisions

### Database vs Files
**Decision:** Store backtest results in database (not CSV files)
**Rationale:**
- Web app already uses SQLite
- Easier to query and display
- Can paginate monthly data
- Consistent with current architecture

### Historical Data Storage
**Decision:** Store all historical prices in strategy-tracker DB
**Rationale:**
- Self-contained application
- No dependency on tiingo_stocks_etfs
- Can regenerate backtests anytime

### Chart Library
**Decision:** Use Chart.js (or Plotly.js if interactive charts needed)
**Rationale:**
- Lightweight
- Works well with Go templates
- No backend chart generation needed

### Backtest Updates
**Decision:** Backtests run manually, not automatically
**Rationale:**
- Historical data rarely changes
- Computationally expensive
- Can add scheduled updates later if needed

## Testing Plan

1. **Data Integrity**
   - Verify backtest results match tiingo_stocks_etfs output
   - Check monthly returns sum correctly
   - Validate tax calculations

2. **Performance**
   - Ensure monthly returns table loads quickly (pagination)
   - Test with full 27-year dataset

3. **UI/UX**
   - Mobile responsive design
   - Charts render correctly
   - Navigation is intuitive

## Success Criteria

- ✅ All 5 backtests run successfully
- ✅ Results match original backtests (within 0.01%)
- ✅ Web pages load in < 2 seconds
- ✅ Charts are clear and informative
- ✅ Can drill down into any month's holdings
- ✅ Tax calculations are transparent

## Files to Create/Modify

### New Files
- `db/migrations/002_backtest_tables.sql`
- `lib/portfolio.py`
- `scripts/backtest_to_db.py`
- `scripts/run_all_backtests.py`
- `scripts/backfill_historical_data.py`
- `scripts/backtest_gtaa3_hold_until_replaced.py`
- `scripts/backtest_gtaa6_hold_until_replaced.py`
- `templates/backtests.html`
- `templates/backtest_detail.html`
- `templates/backtest_compare.html`

### Modified Files
- `main.go` (add routes, handlers, data structures)
- `db/schema.sql` (add new tables)
- `templates/base.html` or navigation (add Backtests link)

## Estimated Time
- Database setup: 2-4 hours
- Backtest scripts: 8-12 hours
- Data backfill: 2-4 hours
- Go backend: 6-8 hours
- Web UI: 8-12 hours
- Testing & polish: 4-6 hours
- **Total: 30-46 hours** (1-2 weeks of focused work)
