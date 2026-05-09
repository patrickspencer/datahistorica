"""Update GTAA 6 backtest results in website database with CORRECT version.

Uses the roc_3_6_12 version which has proper lot-level tax accounting.
"""

import sys
import pandas as pd
from pathlib import Path

# Add parent directory to path for imports
sys.path.append(str(Path(__file__).parent))
from backtest_to_db import save_backtest_results

# Source directory for CORRECT backtest results
SOURCE_DIR = Path('/Users/patrick/Dropbox/programming/tiingo_stocks_etfs/docs/strategy_results/gtaa_agg6_hold_until_replaced_roc_3_6_12')

print("="*80)
print("UPDATING GTAA 6 'HOLD UNTIL REPLACED' BACKTEST")
print("Using CORRECT version with proper tax accounting")
print("="*80)
print()

# Load data
print("Loading data from:", SOURCE_DIR)
monthly_df = pd.read_csv(SOURCE_DIR / 'monthly_returns.csv', parse_dates=['Date'])
annual_df = pd.read_csv(SOURCE_DIR / 'annual_returns_with_taxes.csv')
summary_df = pd.read_csv(SOURCE_DIR / 'summary_with_taxes.csv')

print(f"  ✓ Monthly returns: {len(monthly_df)} rows")
print(f"  ✓ Annual returns: {len(annual_df)} rows")
print(f"  ✓ Summary data loaded")
print()

# Prepare configuration
config = {
    'universe_etfs': ['GSG', 'IAU', 'VBK', 'VWO', 'VBR', 'VEA', 'VTV',
                      'VCIT', 'VGIT', 'IGOV', 'QQQ', 'VNQ', 'MTUM', 'VGLT', 'BIL'],
    'start_date': '1999-01-31',
    'end_date': '2026-05-31',
    'initial_capital': 10000.0,
    'rebalance_frequency': 'monthly',
    'top_n': 6,
    'description': 'GTAA AGG 6 - Hold until replaced strategy using 3,6,12-month ROC average (excluding 1-month). Proper lot-level tax accounting with FIFO.'
}

# Extract metrics from summary
summary = summary_df.iloc[0]
metrics = {
    'period_start': '1999-01-31',
    'period_end': '2026-05-31',
    'years': float(summary['Years']),
    'pre_tax_cagr': float(summary['Pre_Tax_CAGR']),
    'after_tax_cagr': float(summary['After_Tax_CAGR']),
    'tax_drag': float(summary['Tax_Drag']),
    'pre_tax_final': float(summary['Pre_Tax_Final']),
    'after_tax_final': float(summary['After_Tax_Final']),
    'total_taxes': float(summary['Total_Taxes']),
    'effective_tax_rate': float(summary['Effective_Tax_Rate']),
    'max_drawdown': None,  # Not in this summary
    'num_transactions': None
}

print("Metrics to save:")
print(f"  Pre-tax CAGR: {metrics['pre_tax_cagr']:.2%}")
print(f"  After-tax CAGR: {metrics['after_tax_cagr']:.2%}")
print(f"  Tax drag: {metrics['tax_drag']:.2%}")
print(f"  Final value (pre-tax): ${metrics['pre_tax_final']:,.2f}")
print(f"  Final value (after-tax): ${metrics['after_tax_final']:,.2f}")
print(f"  Total taxes: ${metrics['total_taxes']:,.2f}")
print(f"  Effective tax rate: {metrics['effective_tax_rate']:.1%}")
print()

# Save to database
save_backtest_results(
    strategy_name='gtaa6',
    variant='hold_until_replaced',
    monthly_df=monthly_df,
    annual_df=annual_df,
    metrics=metrics,
    config=config
)

print()
print("="*80)
print("✅ DATABASE UPDATE COMPLETE")
print("="*80)
print()
print("The website now uses the CORRECT backtest with:")
print("  • Proper lot-level FIFO tax accounting")
print("  • Accurate gain calculations (proceeds - cost basis)")
print("  • Dynamic position value tracking")
print()
print("Previous 'final' version had critical errors:")
print("  ✗ Wrong gain formula (overstated by up to 25%)")
print("  ✗ Static weights that didn't update with prices")
print("  ✗ No actual share tracking")
print()
