"""
Bot 1: Trend Catcher
Strategy: EMA crossover amb RSI filter per XAUUSD
- Achlt entrance: EMA 8 creua per sobre de EMA 21 en H1
- Confirmació: RSI > 50 (long) o RSI < 50 (short)
- Exit: SL 50 pips, TP 100 pips (2:1 RR)
- Max 3% risk per trade
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib.backtester import Backtester, Bar
from lib.ctrader_client import cTraderClient
import asyncio

# Strategy parameters
EMA_FAST = 8
EMA_SLOW = 21
RSI_PERIOD = 14
RSI_THRESHOLD = 50

class TrendCatcherBot:
    name = "TrendCatcher"
    
    def __init__(self):
        self.fast_emas = []
        self.slow_emas = []
        self.rsis = []
    
    def calc_ema(self, values: list, period: int) -> float:
        if len(values) < period:
            return values[-1] if values else 0
        multiplier = 2 / (period + 1)
        ema = sum(values[:period]) / period
        for price in values[period:]:
            ema = (price - ema) * multiplier + ema
        return ema
    
    def calc_rsi(self, prices: list, period: int = 14) -> float:
        if len(prices) < period + 1:
            return 50
        gains = []
        losses = []
        for i in range(1, len(prices)):
            diff = prices[i] - prices[i-1]
            gains.append(max(diff, 0))
            losses.append(max(-diff, 0))
        
        if len(gains) < period:
            return 50
        
        avg_gain = sum(gains[-period:]) / period
        avg_loss = sum(losses[-period:]) / period
        
        if avg_loss == 0:
            return 100
        rs = avg_gain / avg_loss
        return 100 - (100 / (1 + rs))
    
    def strategy(self, bt: Backtester, i: int) -> dict:
        """
        Called for each bar. Return signal dict or None.
        """
        bar = bt.bars[i]
        
        # Need enough data
        if i < EMA_SLOW + RSI_PERIOD:
            return None
        
        # Get closing prices up to current bar
        closes = [bt.bars[j].close for j in range(max(0, i-50), i+1)]
        
        # Calculate EMAs
        fast_ema = self.calc_ema(closes, EMA_FAST)
        slow_ema = self.calc_ema(closes, EMA_SLOW)
        
        # Calculate RSI
        rsi = self.calc_rsi(closes, RSI_PERIOD)
        
        # Store for next iteration
        if len(self.fast_emas) > 100:
            self.fast_emas.pop(0)
        if len(self.slow_emas) > 100:
            self.slow_emas.pop(0)
        if len(self.rsis) > 100:
            self.rsis.pop(0)
            
        self.fast_emas.append(fast_ema)
        self.slow_emas.append(slow_ema)
        self.rsis.append(rsi)
        
        # Need previous values for crossover detection
        if len(self.fast_emas) < 2 or len(self.slow_emas) < 2:
            return None
        
        prev_fast = self.fast_emas[-2]
        prev_slow = self.slow_emas[-2]
        curr_fast = self.fast_emas[-1]
        curr_slow = self.slow_emas[-1]
        
        # Long signal: fast EMA crosses above slow EMA + RSI confirm
        if prev_fast <= prev_slow and curr_fast > curr_slow and rsi > RSI_THRESHOLD:
            return {
                'direction': 'long',
                'sl_pips': 50,
                'tp_pips': 100,
                'size': bt.balance * 0.02 / (50 * 0.01)  # 2% risk, 50 pip SL
            }
        
        # Short signal: fast EMA crosses below slow EMA + RSI confirm
        if prev_fast >= prev_slow and curr_fast < curr_slow and rsi < (100 - RSI_THRESHOLD):
            return {
                'direction': 'short',
                'sl_pips': 50,
                'tp_pips': 100,
                'size': bt.balance * 0.02 / (50 * 0.01)
            }
        
        return None


async def download_data():
    """Download 6 months of XAUUSD H1 data"""
    from lib.ctrader_client import cTraderClient
    
    client = cTraderClient(
        client_id="25114_k8rMRH0dc60unmMEH6jVmHjM0cRIuqXodKSB4C1C2Gkto4NJ8q",
        client_secret="2JHRsl86n1syeF10pa3HUb7JLMb7tZO6yFlqo14rfi1UVGMu70",
        access_token="zFCkv4Jy6tkHo61uQrmvsyLjpC1kmYRY8DDPspRP_SQ",
        account_id=46755404
    )
    
    connected = await client.connect()
    if not connected:
        print("Failed to connect")
        return []
    
    print("Connected! Downloading XAUUSD H1 data...")
    bars = await client.get_historical_data(symbol_id=1, period=2, days=180)
    
    await client.close()
    
    return bars

def main():
    import time
    
    print("="*60)
    print("Bot 1: Trend Catcher - XAUUSD H1")
    print("="*60)
    
    # Try to load cached data first
    data_file = os.path.join(os.path.dirname(__file__), '../data/xauusd_h1_6m.json')
    
    if os.path.exists(data_file):
        print(f"Loading cached data from {data_file}")
        with open(data_file, 'r') as f:
            import json
            bars_data = json.load(f)
    else:
        # Download data
        bars_data = asyncio.run(download_data())
        
        if bars_data:
            # Cache it
            os.makedirs(os.path.dirname(data_file), exist_ok=True)
            with open(data_file, 'w') as f:
                import json
                json.dump(bars_data, f)
            print(f"Cached data to {data_file}")
    
    if not bars_data:
        print("No data available. Exiting.")
        return
    
    # Run backtest
    bt = Backtester(initial_balance=10000, max_daily_loss_pct=0.03, max_total_loss_pct=0.10)
    bt.load_from_json_bars(bars_data)
    
    bot = TrendCatcherBot()
    
    # Wrap the strategy
    def strategy(bt, i):
        return bot.strategy(bt, i)
    
    result = bt.run(strategy, symbol="XAUUSD", timeframe="H1")
    
    # Save results
    results_file = os.path.join(os.path.dirname(__file__), '../backtests/trend_catcher_results.json')
    bt.save_results(result, results_file)
    
    return result

if __name__ == "__main__":
    main()
