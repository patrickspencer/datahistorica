# Backtest Results Summary

**Generated:** 2026-05-03
**Database:** strategy-tracker/data/strategies.db

## 🎯 All 5 Backtests Complete!

All backtest results are now stored in the database and ready for web UI display.

## Performance Rankings (by After-Tax CAGR)

| Rank | Strategy | Variant | Pre-Tax CAGR | After-Tax CAGR | Final Value | Transactions |
|------|----------|---------|--------------|----------------|-------------|--------------|
| 🥇 1 | GTAA 6 | Hold Until Replaced | **11.33%** | **8.44%** | $187,940 | 1,006 |
| 🥈 2 | GTAA 3 | Hold Until Replaced | **11.28%** | **7.73%** | $185,366 | 736 |
| 🥉 3 | GTAA 6 | Equal Weight | **10.38%** | **7.56%** | $148,652 | 2,031 |
| 4 | GTAA 3 | Equal Weight | **9.82%** | **6.69%** | $129,439 | 1,146 |
| 5 | Dual Momentum | ROC12 + MA200 | **10.83%** | **6.51%** | $204,257 | 725 |

## Key Insights

### 🏆 Winner: GTAA 6 Hold Until Replaced
- **Best after-tax performance:** 8.44% CAGR
- **Lower turnover:** Only 1,006 transactions vs 2,031 for equal-weight
- **Tax efficiency:** 11.33% pre-tax → 8.44% after-tax (2.89% drag)
- **Strategy:** Only rebalance when top 6 assets change (not monthly)

### 📊 Hold vs Equal-Weight Comparison

**GTAA 6:**
- Hold: 11.33% / 8.44% (1,006 txns)
- Equal: 10.38% / 7.56% (2,031 txns)
- **Hold wins by +0.88% after-tax**

**GTAA 3:**
- Hold: 11.28% / 7.73% (736 txns)
- Equal: 9.82% / 6.69% (1,146 txns)
- **Hold wins by +1.04% after-tax**

**Conclusion:** "Hold Until Replaced" dramatically outperforms monthly rebalancing due to lower turnover and better tax efficiency.

### 🎯 GTAA 6 vs GTAA 3

**Hold Until Replaced:**
- GTAA 6: 8.44% after-tax
- GTAA 3: 7.73% after-tax
- **GTAA 6 wins by +0.71%**

**Equal Weight:**
- GTAA 6: 7.56% after-tax
- GTAA 3: 6.69% after-tax
- **GTAA 6 wins by +0.87%**

**Conclusion:** Holding 6 assets provides better diversification and returns than 3 assets.

### ⚠️ Dual Momentum Paradox

- **Highest pre-tax CAGR:** 10.83% (only beat by GTAA 6/3 hold)
- **Highest final value:** $204,257
- **But 5th in after-tax CAGR:** 6.51%
- **Why?** Higher tax drag (4.32%) due to frequent switches between VOO/VEU
- **Longest backtest:** 1997-2026 (29.3 years) vs 1999-2026 for GTAA

## Database Statistics

### Records Stored

| Table | Total Records |
|-------|--------------|
| backtest_configs | 5 |
| backtest_monthly_returns | 1,669 |
| backtest_annual_returns | 144 |
| backtest_metrics | 5 |

### Data Coverage

- **GTAA Strategies:** 1999-01-31 to 2026-05-31 (27.3 years)
- **Dual Momentum:** 1997-01-31 to 2026-05-31 (29.3 years)
- **Monthly data points:** 329-353 per strategy
- **Annual summaries:** 28-30 years per strategy

## Historical Proxy Data

Successfully copied 71,538 price records for 10 mutual funds:
- VFINX (S&P 500) - 7,820 records
- VBMFX (Bonds) - 7,820 records
- VGPMX (Gold) - 7,126 records
- PCRIX (Commodities) - 5,997 records
- VISGX, VISVX, VIVAX, VEIEX, VGTSX (Various equities)
- GLD (Gold 2004-2010) - 5,396 records

## Next Steps

### Phase 4: ✅ Complete
- All backtests run successfully
- All data saved to database
- Verified data integrity

### Phase 5: 🚧 Ready to Start - Go Backend
- [ ] Add routes (`/backtests`, `/backtests/{strategy}`)
- [ ] Create Go data structures
- [ ] Write database query functions
- [ ] Test API endpoints

### Phase 6: 🚧 Ready to Start - Web UI
- [ ] Create `templates/backtests.html` (main comparison page)
- [ ] Create `templates/backtest_detail.html` (individual strategy pages)
- [ ] Add charts (Chart.js or Plotly)
- [ ] Add navigation links
- [ ] Style tables and layout

## Files Created

### Core Infrastructure
- `lib/portfolio.py` - Shared Portfolio class with tax tracking
- `scripts/backtest_to_db.py` - Database helper functions
- `scripts/copy_proxy_data.py` - Historical data migration

### Backtest Scripts
- `scripts/backtest_gtaa6_equal_weight.py`
- `scripts/backtest_gtaa6_hold_until_replaced.py`
- `scripts/backtest_gtaa3_equal_weight.py`
- `scripts/backtest_gtaa3_hold_until_replaced.py`
- `scripts/backtest_dual_momentum_roc12.py`

### Documentation
- `BACKTEST_INTEGRATION_PLAN.md` - Full integration plan
- `BACKTEST_RESULTS_SUMMARY.md` - This file

## Quick Commands

```bash
# View all backtest configs
sqlite3 data/strategies.db "SELECT * FROM backtest_configs;"

# View performance metrics
sqlite3 data/strategies.db "SELECT * FROM backtest_metrics;"

# Re-run a specific backtest
python scripts/backtest_gtaa6_hold_until_replaced.py

# Check monthly returns for a strategy
sqlite3 data/strategies.db "SELECT * FROM backtest_monthly_returns WHERE config_id = 4 LIMIT 10;"
```

## Estimated Remaining Work

- **Go Backend:** 6-8 hours
- **Web UI:** 8-12 hours
- **Testing & Polish:** 2-4 hours
- **Total:** 16-24 hours

The heavy lifting is done! All backtest logic is working, data is in the database, and infrastructure is solid. The remaining work is primarily front-end display.
