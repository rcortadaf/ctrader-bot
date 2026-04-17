"""
Momentum Catch Bot
Strategy: Captures strong momentum moves after consolidation
- Uses RSI for momentum detection (oversold/overbought)
- EMA crossover for trend confirmation  
- Volume surge for momentum validation
- Fixed pip-based stop loss and take profit for XAUUSD H1 timeframe
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from lib.backtester import Backtester, Bar
import json


class MomentumCatchBot:
    name = "MomentumCatch"
    
    def __init__(self, rsi_period=14, ema_fast=8, ema_slow=21, sl_pips=80, tp_pips=160, 
                 rsi_oversold=35, rsi_overbought=65, volume_ma=20):
        self.rsi_period = rsi_period
        self.ema_fast = ema_fast
        self.ema_slow = ema_slow
        self.sl_pips = sl_pips
        self.tp_pips = tp_pips
        self.rsi_oversold = rsi_oversold
        self.rsi_overbought = rsi_overbought
        self.volume_ma = volume_ma
        self.last_trade_idx = -100
        
    def calc_rsi(self, bt, i, period=14):
        """Calculate RSI indicator"""
        if i < period:
            return 50.0
        
        gains = []
        losses = []
        for j in range(max(1, i - period + 1), i + 1):
            delta = bt.bars[j].close - bt.bars[j-1].close
            if delta >= 0:
                gains.append(delta)
                losses.append(0)
            else:
                gains.append(0)
                losses.append(abs(delta))
        
        avg_gain = sum(gains) / len(gains)
        avg_loss = sum(losses) / len(losses)
        
        if avg_loss == 0:
            return 100.0
        rs = avg_gain / avg_loss
        return 100 - (100 / (1 + rs))
    
    def calc_ema(self, values: list, period: int) -> float:
        if len(values) < period:
            return values[-1] if values else 0
        multiplier = 2 / (period + 1)
        ema = sum(values[:period]) / period
        for price in values[period:]:
            ema = (price - ema) * multiplier + ema
        return ema
    
    def calc_ema_on_bars(self, bt, i, period: int, attr='close') -> float:
        """Calculate EMA on bar attributes"""
        if i < period:
            return getattr(bt.bars[i], attr)
        values = [getattr(bt.bars[k], attr) for k in range(max(0, i - period + 1), i + 1)]
        return self.calc_ema(values, period)
    
    def calc_volume_ma(self, bt, i, period=20):
        """Calculate volume moving average"""
        if i < period:
            vol_values = [bt.bars[k].volume for k in range(0, i + 1)]
        else:
            vol_values = [bt.bars[k].volume for k in range(i - period + 1, i + 1)]
        return sum(vol_values) / len(vol_values) if vol_values else 50
    
    def strategy(self, bt, i) -> dict:
        """Momentum Catch Strategy"""
        bar = bt.bars[i]
        
        # Need enough bars for calculations
        min_bars = max(self.rsi_period, self.ema_slow, self.volume_ma) + 5
        if i < min_bars:
            return None
        
        # Cooldown period between trades
        if i - self.last_trade_idx < 3:
            return None
        
        # Calculate indicators
        rsi = self.calc_rsi(bt, i, self.rsi_period)
        ema_fast = self.calc_ema_on_bars(bt, i, self.ema_fast)
        ema_slow = self.calc_ema_on_bars(bt, i, self.ema_slow)
        
        # Calculate volume MA
        vol_ma = self.calc_volume_ma(bt, i, self.volume_ma)
        
        # Calculate price momentum (rate of change)
        if i >= 10:
            price_change_pct = (bar.close - bt.bars[i-10].close) / bt.bars[i-10].close * 100
        else:
            price_change_pct = 0
        
        # === Bullish Momentum Setup ===
        # RSI oversold and EMA crossover bullish, with volume surge
        prev_ema_fast = self.calc_ema_on_bars(bt, i - 1, self.ema_fast)
        prev_ema_slow = self.calc_ema_on_bars(bt, i - 1, self.ema_slow)
        
        bullish_cross = (prev_ema_fast <= prev_ema_slow) and (ema_fast > ema_slow)
        volume_surge = bar.volume > vol_ma * 1.3
        
        if rsi < self.rsi_oversold and bullish_cross and volume_surge:
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
        
        # === Bearish Momentum Setup ===
        # RSI overbought and EMA crossover bearish, with volume surge
        bearish_cross = (prev_ema_fast >= prev_ema_slow) and (ema_fast < ema_slow)
        
        if rsi > self.rsi_overbought and bearish_cross and volume_surge:
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
    print("Momentum Catch Bot - XAUUSD H1")
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
    
    bot = MomentumCatchBot(
        rsi_period=14,
        ema_fast=8,
        ema_slow=21,
        sl_pips=80,
        tp_pips=160,
        rsi_oversold=35,
        rsi_overbought=65,
        volume_ma=20
    )
    
    def strategy(bt, i):
        return bot.strategy(bt, i)
    
    result = bt.run(strategy, symbol="XAUUSD", timeframe="H1")
    
    # Save results
    results_file = os.path.join(os.path.dirname(__file__), '../../backtests/momentum_catch_results.json')
    bt.save_results(result, results_file)
    
    return result


if __name__ == "__main__":
    main()