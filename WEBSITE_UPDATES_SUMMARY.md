# Website Updates Summary

**Date:** 2026-05-04
**Updates:** Monthly returns fix, UI cleanup, backtest naming

## Changes Made

### 1. Fixed Monthly Returns Display ✅

**Issue:** Monthly returns table on backtest detail pages was empty due to template bug.

**Fix:** Removed broken counter logic in `templates/backtest_detail.html`:
- **Before:** Used `{{$count := 0}}` and `{{$count = add $count 1}}` (doesn't work in Go templates)
- **After:** Simple `{{range .MonthlyReturns}}` loop

**Result:** All 120 monthly returns now display correctly on each backtest detail page.

### 2. Cleaned Up Backtests Comparison Page ✅

**Removed from `/backtests`:**
- Meta-box section (historical performance analysis intro)
- Key-insights cards (top performer, highest value, lowest turnover)
- Rank column from comparison table

**Result:** Cleaner, more focused comparison table.

### 3. Renamed Backtests for Clarity ✅

**Problem:** Hard to distinguish 15-ETF universe (with QQQ/EFA) from 13-ETF universe (without).

**Solution:** Updated variant names in database:

**Before:**
- gtaa6 - equal_weight
- gtaa6 - hold_until_replaced  
- gtaa6 - equal_weight_original13
- gtaa6 - hold_until_replaced_original13

**After:**
- gtaa6 - **equal_weight_extended** (15 ETFs with QQQ, EFA)
- gtaa6 - **hold_until_replaced_extended** (15 ETFs with QQQ, EFA)
- gtaa6 - equal_weight_original13 (13 ETFs, no QQQ/EFA)
- gtaa6 - hold_until_replaced_original13 (13 ETFs, no QQQ/EFA)

**Same for GTAA 3:**
- gtaa3 - **equal_weight_extended** (15 ETFs)
- gtaa3 - **hold_until_replaced_extended** (15 ETFs)

## Current Backtest Inventory

All 7 backtests in database with clear naming:

| ID | Strategy | Variant | Universe | After-Tax CAGR |
|----|----------|---------|----------|----------------|
| 6 | dual_momentum | roc12_ma200 | 2 ETFs | 6.51% |
| 3 | gtaa3 | equal_weight_extended | 15 ETFs | 6.69% |
| 5 | gtaa3 | hold_until_replaced_extended | 15 ETFs | 7.73% |
| 2 | gtaa6 | equal_weight_extended | 15 ETFs | 7.56% |
| 4 | gtaa6 | hold_until_replaced_extended | 15 ETFs | 8.44% |
| 7 | gtaa6 | equal_weight_original13 | 13 ETFs | 6.86% |
| 8 | gtaa6 | hold_until_replaced_original13 | 13 ETFs | 7.81% |

## Naming Convention

- **extended** = 15 ETF universe (includes QQQ, EFA)
- **original13** = 13 ETF universe (original GTAA 13, no QQQ/EFA)

## Files Modified

1. `templates/backtest_detail.html` - Fixed monthly returns loop
2. `templates/backtests.html` - Removed meta-box, key-insights, rank column
3. `data/strategies.db` - Updated variant names and descriptions

## Verification

Test the changes:

```bash
# Check monthly returns appear
curl http://localhost:8080/backtests/detail?strategy=gtaa6&variant=hold_until_replaced_extended

# Check backtests page has no rank column
curl http://localhost:8080/backtests | grep "Rank"  # Should return nothing

# Verify new variant names in database
sqlite3 data/strategies.db "SELECT id, strategy_name, variant FROM backtest_configs;"
```

## What Users See Now

### On Backtest Detail Pages:
- ✅ Monthly returns table with 120 rows (newest first)
- ✅ Holdings shown for each month
- ✅ Clear variant names (extended vs original13)

### On Backtests Comparison Page:
- ✅ Clean table without rank column
- ✅ No meta-box or insight cards
- ✅ Direct access to comparison data

### On Portfolio Pages:
- ✅ Backtest tables show both extended and original13 variants
- ✅ Clear labeling of which universe each uses

## Next Steps

Future enhancements could include:
- [ ] Add toggle to switch between extended and original13 on charts
- [ ] Add universe composition details to backtest pages
- [ ] Create comparison chart showing extended vs original13 performance
