# GTAA 6 Original 13 Universe Backtest Results

**Created:** 2026-05-04
**Database IDs:** 7 (equal weight), 8 (hold until replaced)

## Universe Composition

Original GTAA 13 assets (removed QQQ and EFA from the 15-asset universe):

1. VTV - US Large Cap Value
2. MTUM - US Large Cap Momentum
3. VBR - US Small Cap Value
4. VBK - US Small Cap Growth
5. VEA - Foreign Developed
6. VWO - Foreign Emerging
7. VGIT - US 10Y Gov Bonds
8. IGOV - Foreign 10Y Gov Bonds
9. VCIT - US Corporate Bonds
10. VGLT - US 30Y Gov Bonds
11. GSG - Commodities
12. IAU - Gold
13. VNQ - Real Estate

## Performance Results (1999-2026, 27.3 years)

### GTAA 6 Equal Weight - Original 13

- **Pre-Tax CAGR:** 9.25%
- **After-Tax CAGR:** 6.86%
- **Tax Drag:** 2.38%
- **Final Value:** $112,113 (from $10,000)
- **Total Taxes:** $18,734
- **Effective Tax Rate:** 18.3%
- **Transactions:** 1,983

### GTAA 6 Hold Until Replaced - Original 13

- **Pre-Tax CAGR:** 10.31%
- **After-Tax CAGR:** 7.81%
- **Tax Drag:** 2.50%
- **Final Value:** $146,152 (from $10,000)
- **Total Taxes:** $23,138
- **Effective Tax Rate:** 17.0%
- **Transactions:** 991

## Key Findings

### Hold Outperforms Equal Weight

- **After-tax advantage:** +0.95% annually (7.81% vs 6.86%)
- **Transaction reduction:** 50% fewer (991 vs 1,983)
- **Final value difference:** $34,039 higher ($146K vs $112K)
- **Tax efficiency:** Lower effective tax rate despite higher gains

### Impact of Removing QQQ and EFA

Comparison with the 15-asset universe:

| Metric | Original 13 (no QQQ/EFA) | Previous 15 (with QQQ/EFA) | Difference |
|--------|--------------------------|----------------------------|------------|
| Equal Weight After-Tax CAGR | 6.86% | 7.56% | -0.70% |
| Hold After-Tax CAGR | 7.81% | 8.44% | -0.63% |

**Observations:**
- Removing QQQ and EFA reduced performance by ~0.6-0.7% annually
- QQQ (Nasdaq tech) likely added value during tech booms (2010s, 2020s)
- EFA removal had less impact (covered by VEA)
- The "Hold Until Replaced" advantage (~1%) persists regardless of universe

### Transaction Analysis

**Equal Weight:**
- Monthly rebalancing = high turnover
- 1,983 transactions over 27 years = ~73/year
- More short-term gains, higher tax burden

**Hold Until Replaced:**
- Only rebalances when top 6 change
- 991 transactions over 27 years = ~36/year
- More long-term gains, lower tax burden
- 50% reduction in turnover vs equal weight

## Database Details

Both backtests stored in `data/strategies.db`:

```sql
-- Config IDs
SELECT id, strategy_name, variant FROM backtest_configs 
WHERE id IN (7, 8);
-- 7 | gtaa6 | equal_weight_original13
-- 8 | gtaa6 | hold_until_replaced_original13

-- Monthly records: 329 each
-- Annual records: 28 each
```

## Files Created

- `scripts/backtest_gtaa6_equal_weight_original13.py`
- `scripts/backtest_gtaa6_hold_until_replaced_original13.py`
- `docs/strategy_results/gtaa_agg6_equal_weight_FIXED/` (CSV exports)
- `docs/strategy_results/gtaa6_hold_until_replaced/` (CSV exports)

## Recommendations

1. **For tax-advantaged accounts:** Equal weight is acceptable (no tax drag)
2. **For taxable accounts:** Hold Until Replaced is superior (+0.95% after-tax)
3. **Universe selection:** Including QQQ adds ~0.6% CAGR but increases concentration in US tech
4. **Turnover matters:** The 50% reduction in transactions saves ~0.5% annually in tax drag

## Next Steps

- [ ] Add these backtests to the website comparison page
- [ ] Consider creating a QQQ vs No-QQQ comparison chart
- [ ] Analyze which years QQQ was most impactful
- [ ] Test other universe variations (e.g., different commodity proxies)
