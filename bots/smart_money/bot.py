"""
Bot 2: Smart Money Concepts (SMC)
Strategy: Institutional price action using SMC principles
- Fair Value Gaps (FVG): Imbalances in price action
- EMA crossover for trend detection
- Entry on retest of FVG zones aligned with trend
- Max 2% risk per trade
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from lib.backtester import Backtester, Bar
import json


class SmartMoneyBot:
    name = "SmartMoneyConcepts"
    
    def __init__(self):
        self.fvgs = []
        self.trend = None
        self.last_trade_idx = -100
        self.crossover_just_happened = False
        
    def calc_ema(self, values: list, period: int) -> float:
        if len(values) < period:
            return values[-1] if values else 0
        multiplier = 2 / (period + 1)
        ema = sum(values[:period]) / period
        for price in values[period:]:
            ema = (price - ema) * multiplier + ema
        return ema
    
    def detect_fvg(self, bt, i):
        """Detect Fair Value Gap - gap between candle i-2 and i"""
        if i < 2:
            return None
            
        bar_prev = bt.bars[i-2]
        bar_curr = bt.bars[i]
        
        # Bullish FVG
        if bar_curr.low > bar_prev.high:
            return {
                'type': 'bullish',
                'index': i,
                'top': bar_curr.low,
                'bottom': bar_prev.high
            }
        
        # Bearish FVG
        if bar_curr.high < bar_prev.low:
            return {
                'type': 'bearish',
                'index': i,
                'top': bar_prev.low,
                'bottom': bar_curr.high
            }
        
        return None
    
    def strategy(self, bt, i) -> dict:
        """SMC Strategy"""
        bar = bt.bars[i]
        
        if i < 50:
            return None
        
        # Cooldown period between trades
        if i - self.last_trade_idx < 20:
            return None
        
        # === Trend Detection using EMA crossover ===
        closes = [bt.bars[j].close for j in range(max(0, i-50), i+1)]
        ema_fast = self.calc_ema(closes, 8)
        ema_slow = self.calc_ema(closes, 21)
        
        prev_fast = self.calc_ema(closes[:-1], 8) if len(closes) > 1 else ema_fast
        prev_slow = self.calc_ema(closes[:-1], 21) if len(closes) > 1 else ema_slow
        
        # Detect crossover
        crossover = None
        if prev_fast <= prev_slow and ema_fast > ema_slow:
            crossover = 'bullish'
        elif prev_fast >= prev_slow and ema_fast < ema_slow:
            crossover = 'bearish'
        
        if crossover:
            self.crossover_just_happened = True
            self.trend = crossover
        
        # === Detect FVG ===
        fvg = self.detect_fvg(bt, i)
        if fvg:
            self.fvgs.append(fvg)
            if len(self.fvgs) > 30:
                self.fvgs.pop(0)
        
        # === Entry Logic ===
        # Only enter if we have a clear trend
        if not self.trend:
            return None
        
        # === Long Entry ===
        if self.trend == 'bullish':
            # Look for bullish FVG retests
            for fvg in reversed(self.fvgs[-10:]):  # Last 10 FVGs
                if fvg['type'] == 'bullish':
                    entry_zone = fvg['bottom']
                    # Price is at/near the FVG zone
                    if abs(bar.close - entry_zone) < 20 * 0.01:
                        sl = entry_zone - 50 * 0.01
                        tp = bar.close + 100 * 0.01  # 2:1 RR
                        
                        if sl < bar.close and tp > bar.close:
                            self.last_trade_idx = i
                            return {
                                'direction': 'long',
                                'sl_pips': 50,
                                'tp_pips': 100,
                                'size': bt.balance * 0.02 / (50 * 0.01)
                            }
                    break  # Only use most recent FVG
        
        # === Short Entry ===
        if self.trend == 'bearish':
            for fvg in reversed(self.fvgs[-10:]):
                if fvg['type'] == 'bearish':
                    entry_zone = fvg['top']
                    if abs(bar.close - entry_zone) < 20 * 0.01:
                        sl = entry_zone + 50 * 0.01
                        tp = bar.close - 100 * 0.01
                        
                        if sl > bar.close and tp < bar.close:
                            self.last_trade_idx = i
                            return {
                                'direction': 'short',
                                'sl_pips': 50,
                                'tp_pips': 100,
                                'size': bt.balance * 0.02 / (50 * 0.01)
                            }
                    break
        
        return None


def main():
    print("="*60)
    print("Bot 2: Smart Money Concepts - XAUUSD H1")
    print("="*60)
    
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
    
    bot = SmartMoneyBot()
    
    def strategy(bt, i):
        return bot.strategy(bt, i)
    
    result = bt.run(strategy, symbol="XAUUSD", timeframe="H1")
    
    # Save results
    results_file = os.path.join(os.path.dirname(__file__), '../../backtests/smart_money_results.json')
    bt.save_results(result, results_file)
    
    return result


if __name__ == "__main__":
    main()