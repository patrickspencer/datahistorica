"""Calculate drawdown statistics for all backtests from monthly returns data."""

import sqlite3
import pandas as pd
from datetime import datetime

def calculate_drawdown(monthly_values, dates):
    """Calculate drawdown statistics from a series of portfolio values."""
    # Convert to pandas Series for easier manipulation
    values = pd.Series(monthly_values, index=pd.to_datetime(dates))
    
    # Calculate running maximum (peak)
    running_max = values.expanding().max()
    
    # Calculate drawdown at each point
    drawdown = (values - running_max) / running_max
    
    # Find the maximum drawdown
    max_dd = drawdown.min()
    max_dd_date = drawdown.idxmin()
    
    if pd.isna(max_dd) or max_dd >= 0:
        # No drawdown occurred
        return None
    
    # Find the peak before the trough
    trough_idx = values.index.get_loc(max_dd_date)
    peak_value = running_max.iloc[trough_idx]
    peak_date = None
    
    # Look backwards from trough to find when we were at peak
    for i in range(trough_idx, -1, -1):
        if values.iloc[i] >= peak_value * 0.9999:  # Allow tiny rounding errors
            peak_date = values.index[i]
            break
    
    if peak_date is None:
        peak_date = values.index[0]
    
    # Find recovery date (when value exceeded the peak again)
    recovery_date = None
    for i in range(trough_idx + 1, len(values)):
        if values.iloc[i] >= peak_value:
            recovery_date = values.index[i]
            break
    
    # Calculate durations
    peak_to_trough_months = None
    trough_to_recovery_months = None
    total_months = None
    
    if peak_date and max_dd_date:
        peak_to_trough_months = (max_dd_date.year - peak_date.year) * 12 + (max_dd_date.month - peak_date.month)
    
    if recovery_date and max_dd_date:
        trough_to_recovery_months = (recovery_date.year - max_dd_date.year) * 12 + (recovery_date.month - max_dd_date.month)
    
    if peak_date and recovery_date:
        total_months = (recovery_date.year - peak_date.year) * 12 + (recovery_date.month - peak_date.month)
    
    return {
        'max_drawdown': float(max_dd),
        'peak_date': peak_date.date().isoformat() if peak_date else None,
        'trough_date': max_dd_date.date().isoformat() if max_dd_date else None,
        'recovery_date': recovery_date.date().isoformat() if recovery_date else None,
        'peak_to_trough_months': peak_to_trough_months,
        'trough_to_recovery_months': trough_to_recovery_months,
        'total_duration_months': total_months
    }

def main():
    conn = sqlite3.connect('data/strategies.db')
    cursor = conn.cursor()
    
    # Get all backtest configs
    cursor.execute("SELECT id, strategy_name, variant FROM backtest_configs")
    configs = cursor.fetchall()
    
    print("Calculating drawdowns for all backtests...")
    print("=" * 80)
    
    for config_id, strategy_name, variant in configs:
        print(f"\n{strategy_name} - {variant} (ID: {config_id})")
        
        # Get monthly returns for this backtest (use after-tax values)
        cursor.execute("""
            SELECT date, after_tax_value 
            FROM backtest_monthly_returns 
            WHERE config_id = ? 
            ORDER BY date ASC
        """, (config_id,))
        
        rows = cursor.fetchall()
        if not rows:
            print(f"  No monthly data found")
            continue
        
        dates = [row[0] for row in rows]
        values = [row[1] for row in rows]
        
        # Calculate drawdown
        dd_stats = calculate_drawdown(values, dates)
        
        if dd_stats is None:
            print(f"  No significant drawdown")
            continue
        
        print(f"  Max Drawdown: {dd_stats['max_drawdown']:.2%}")
        print(f"  Peak Date: {dd_stats['peak_date']}")
        print(f"  Trough Date: {dd_stats['trough_date']}")
        print(f"  Recovery Date: {dd_stats['recovery_date'] or 'Not recovered yet'}")
        print(f"  Peak to Trough: {dd_stats['peak_to_trough_months']} months")
        if dd_stats['trough_to_recovery_months']:
            print(f"  Trough to Recovery: {dd_stats['trough_to_recovery_months']} months")
        if dd_stats['total_duration_months']:
            print(f"  Total Duration: {dd_stats['total_duration_months']} months")
        
        # Update database
        cursor.execute("""
            UPDATE backtest_metrics 
            SET max_drawdown = ?,
                max_dd_peak_date = ?,
                max_dd_trough_date = ?,
                max_dd_recovery_date = ?,
                max_dd_duration_months = ?
            WHERE config_id = ?
        """, (
            dd_stats['max_drawdown'],
            dd_stats['peak_date'],
            dd_stats['trough_date'],
            dd_stats['recovery_date'],
            dd_stats['total_duration_months'],
            config_id
        ))
    
    conn.commit()
    conn.close()
    
    print("\n" + "=" * 80)
    print("✅ Drawdown calculations complete and saved to database")

if __name__ == '__main__':
    main()
