"""
Breakout Hunter Bot
Strategy: Captures momentum breakouts using ATR-filtered range expansion
- Identifies consolidation phases using rolling high/low ranges
- Confirms breakouts with volume confirmation
- Fixed pip-based stop loss and take profit for XAUUSD H1 timeframe
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from lib.backtester import Backtester, Bar
import json


class BreakoutHunterBot:
    name = "BreakoutHunter"
    
    def __init__(self, lookback_period=20, sl_pips=100, tp_pips=200, volume_ma=20):
        self.lookback_period = lookback_period
        self.sl_pips = sl_pips
        self.tp_pips = tp_pips
        self.volume_ma = volume_ma
        self.last_trade_idx = -100
        
    def calc_atr(self, bt, i, period=14):
        """Calculate Average True Range"""
        if i < period:
            return 0.033  # Default ATR from context
        
        tr_values = []
        for j in range(max(1, i - period + 1), i + 1):
            high = bt.bars[j].high
            low = bt.bars[j].low
            prev_close = bt.bars[j-1].close
            
            tr = max(
                high - low,
                abs(high - prev_close),
                abs(low - prev_close)
            )
            tr_values.append(tr)
        
        return sum(tr_values) / len(tr_values) if tr_values else 0.033
    
    def calc_ema(self, values: list, period: int) -> float:
        if len(values) < period:
            return values[-1] if values else 0
        multiplier = 2 / (period + 1)
        ema = sum(values[:period]) / period
        for price in values[period:]:
            ema = (price - ema) * multiplier + ema
        return ema
    
    def calc_highest(self, bt, start: int, end: int, attr='high'):
        """Get highest value in range"""
        values = [getattr(bt.bars[k], attr) for k in range(start, end + 1)]
        return max(values) if values else 0
    
    def calc_lowest(self, bt, start: int, end: int, attr='low'):
        """Get lowest value in range"""
        values = [getattr(bt.bars[k], attr) for k in range(start, end + 1)]
        return min(values) if values else 0
    
    def strategy(self, bt, i) -> dict:
        """Breakout Hunter Strategy - Simple momentum breakout"""
        bar = bt.bars[i]
        
        # Need enough bars for calculation
        if i < self.lookback_period + self.volume_ma:
            return None
        
        # Cooldown period between trades
        if i - self.last_trade_idx < 5:
            return None
        
        # Calculate lookback high/low
        range_start = i - self.lookback_period
        range_end = i - 1
        
        highest_in_range = self.calc_highest(bt, range_start, range_end, 'high')
        lowest_in_range = self.calc_lowest(bt, range_start, range_end, 'low')
        
        # Calculate volume MA
        vol_start = i - self.volume_ma
        vol_values = [bt.bars[k].volume for k in range(vol_start, i)]
        avg_volume = sum(vol_values) / len(vol_values) if vol_values else 50
        
        # === Bullish Breakout Detection ===
        # Price closes above highest high of lookback period
        # with above-average volume
        if bar.close > highest_in_range and bar.volume > avg_volume:
            sl = bar.close - self.sl_pips * 0.01
            tp = bar.close + self.tp_pips * 0.01
            
            if sl < bar.close and tp > bar.close:
                self.last_trade_idx = i
                return {
                    'direction': 'long',
                    'sl_pips': self.sl_pips,
                    'tp_pips': self.tp_pips,
                    'size': bt.balance * 0.02 / (self.sl_pips * 0.01)
                }
        
        # === Bearish Breakout Detection ===
        # Price closes below lowest low of lookback period
        # with above-average volume
        if bar.close < lowest_in_range and bar.volume > avg_volume:
            sl = bar.close + self.sl_pips * 0.01
            tp = bar.close - self.tp_pips * 0.01
            
            if sl > bar.close and tp < bar.close:
                self.last_trade_idx = i
                return {
                    'direction': 'short',
                    'sl_pips': self.sl_pips,
                    'tp_pips': self.tp_pips,
                    'size': bt.balance * 0.02 / (self.sl_pips * 0.01)
                }
        
        return None


def main():
    print("=" * 60)
    print("Breakout Hunter Bot - XAUUSD H1")
    print("=" * 60)
    
    # Load data
    data_file = os.path.join(os.path.dirname(__file__), '../../data/xauusd_h1_6m.json')
    
    if os.path.exists(data_file):
        print(f"Loading data from {data_file}")
        with open(data_file, 'r') as f:
            bars_data = json.load(f)
    else:
        print("Data file not found. Exiting.")
        return None
    
    if not bars_data:
        print("No data available. Exiting.")
        return None
    
    print(f"Loaded {len(bars_data)} bars")
    
    # Run backtest
    bt = Backtester(initial_balance=10000, max_daily_loss_pct=0.03, max_total_loss_pct=0.10)
    bt.load_from_json_bars(bars_data)
    
    bot = BreakoutHunterBot(lookback_period=20, sl_pips=100, tp_pips=200, volume_ma=20)
    
    def strategy(bt, i):
        return bot.strategy(bt, i)
    
    result = bt.run(strategy, symbol="XAUUSD", timeframe="H1")
    
    # Save results
    results_file = os.path.join(os.path.dirname(__file__), '../../backtests/breakout_hunter_results.json')
    bt.save_results(result, results_file)
    
    return result


if __name__ == "__main__":
    main()
