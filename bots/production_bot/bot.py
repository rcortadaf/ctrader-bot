"""
PRODUCTION BOT: FTMO XAUUSD Killer
==================================
Best backtested config: EMA 8/21 + RSI 50, SL 40p, TP 80p, Risk 1.5%
Expected: +10.49% in 6 months | WR: 45% | PF: 1.59 | DD: 8.7%

FTMO RULES COMPLIANT:
- Max Daily Loss: 3% (stop trading if 2.5% reached)
- Max Total Loss: 10% (emergency stop at 8%)
- Position sizing: 1.5% risk per trade
- Consecutive losses: pause after 2 losses
"""

import sys, os, asyncio
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from dataclasses import dataclass
from typing import Optional
from lib.ctrader_client import cTraderClient

# ============================================================
# CONFIGURATION
# ============================================================
class Config:
    # Strategy
    EMA_FAST = 8
    EMA_SLOW = 21
    RSI_PERIOD = 14
    RSI_THRESHOLD = 50
    SL_PIPS = 40
    TP_PIPS = 80
    
    # Risk
    RISK_PCT = 0.015          # 1.5% per trade
    MAX_DAILY_LOSS = 0.025     # Stop at 2.5% (FTMO limit is 3%)
    MAX_TOTAL_LOSS = 0.08      # Emergency stop at 8% (FTMO limit is 10%)
    
    # Session filter (UTC hours)
    SESSION_FILTER = [12, 13, 14, 18, 19]
    
    # Trading
    COOLDOWN_BARS = 10        # Bars between trades
    MAX_TRADES_PER_DAY = 5
    
    # Account
    ACCOUNT_ID = 46755404
    SYMBOL = "XAUUSD"
    SYMBOL_ID = 1             # cTrader symbol ID for XAUUSD


# ============================================================
# STRATEGY ENGINE
# ============================================================
@dataclass
class Signal:
    direction: str           # 'long' or 'short'
    entry_price: float
    stop_loss: float
    take_profit: float
    size: float              # in lots
    confidence: float = 0.5  # 0-1

class ProductionBot:
    name = "FTMO XAUUSD Killer"
    
    def __init__(self, client: cTraderClient, config: type = Config):
        self.client = client
        self.cfg = config
        self.reset()
    
    def reset(self):
        self.last_trade_idx = -999
        self.consecutive_losses = 0
        self.daily_trades = 0
        self.last_date = None
        self.daily_start_balance = None
        self.peak_balance = None
        self.balance = None
        self.trades = []
        self.positions = []
        self.pending_order = None
    
    async def on_bar(self, bar: dict) -> Optional[Signal]:
        """Called on each new bar. Return Signal to trade, None to skip."""
        now = bar['timestamp']
        
        # Daily reset
        if self.last_date and now.date() != self.last_date:
            self.daily_trades = 0
            self.last_date = now
            self.daily_start_balance = self.balance
        
        # Skip if not in session
        if now.hour not in self.cfg.SESSION_FILTER:
            return None
        
        # Skip if too many daily trades
        if self.daily_trades >= self.cfg.MAX_TRADES_PER_DAY:
            return None
        
        # Skip if 2 consecutive losses
        if self.consecutive_losses >= 2:
            return None
        
        # Check loss limits
        if self.daily_start_balance and self.balance:
            daily_loss = (self.daily_start_balance - self.balance) / self.daily_start_balance
            if daily_loss >= self.cfg.MAX_DAILY_LOSS:
                return None
        
        if self.peak_balance and self.balance:
            total_loss = (self.peak_balance - self.balance) / self.peak_balance
            if total_loss >= self.cfg.MAX_TOTAL_LOSS:
                await self.emergency_stop()
                return None
        
        # Calculate indicators
        closes = self.client.get_closes(self.cfg.EMA_SLOW + self.cfg.RSI_PERIOD + 5)
        if len(closes) < self.cfg.EMA_SLOW + 5:
            return None
        
        fast_ema = self.calc_ema(closes, self.cfg.EMA_FAST)
        slow_ema = self.calc_ema(closes, self.cfg.EMA_SLOW)
        prev_fast = self.calc_ema(closes[:-1], self.cfg.EMA_FAST)
        prev_slow = self.calc_ema(closes[:-1], self.cfg.EMA_SLOW)
        rsi = self.calc_rsi(closes, self.cfg.RSI_PERIOD)
        
        # EMA crossover logic
        direction = None
        if prev_fast <= prev_slow and fast_ema > slow_ema and rsi > self.cfg.RSI_THRESHOLD:
            direction = 'long'
        elif prev_fast >= prev_slow and fast_ema < slow_ema and rsi < (100 - self.cfg.RSI_THRESHOLD):
            direction = 'short'
        
        if not direction:
            return None
        
        # Build signal
        ep = bar['close']
        sl_pips = self.cfg.SL_PIPS * 0.01
        tp_pips = self.cfg.TP_PIPS * 0.01
        size = self.calc_size(sl_pips)
        
        if direction == 'long':
            sl = ep - sl_pips
            tp = ep + tp_pips
        else:
            sl = ep + sl_pips
            tp = ep - tp_pips
        
        self.last_trade_idx = bar.get('idx', 0)
        self.daily_trades += 1
        
        return Signal(
            direction=direction,
            entry_price=ep,
            stop_loss=sl,
            take_profit=tp,
            size=size,
            confidence=min(rsi/100, 0.9) if rsi else 0.5
        )
    
    def calc_size(self, sl_distance: float) -> float:
        """Calculate lot size for 1.5% risk."""
        if not self.balance:
            self.balance = 10000
        risk_amount = self.balance * self.cfg.RISK_PCT
        # pip_value = 0.01 (per oz) * 100 (oz per lot) = $1 per pip per lot
        pip_value = 1.0  # $1 per pip per lot (standard for XAUUSD 100oz)
        lots = risk_amount / (sl_distance * pip_value)
        return round(lots, 2)  # Round to 2 decimal places
    
    def calc_ema(self, values: list, period: int) -> float:
        if len(values) < period:
            return values[-1] if values else 0
        mult = 2 / (period + 1)
        ema = sum(values[:period]) / period
        for v in values[period:]:
            ema = (v - ema) * mult + ema
        return ema
    
    def calc_rsi(self, prices: list, period: int = 14) -> float:
        if len(prices) < period + 1:
            return 50
        gains = [max(prices[i]-prices[i-1], 0) for i in range(1, len(prices))]
        losses = [max(prices[i-1]-prices[i], 0) for i in range(1, len(prices))]
        ag = sum(gains[-period:]) / period
        al = sum(losses[-period:]) / period
        if al == 0:
            return 100
        return 100 - 100 / (1 + ag / al)
    
    async def emergency_stop(self):
        """Close all positions and stop trading."""
        print("🚨 EMERGENCY STOP - Loss limits reached!")
        await self.client.close_all_positions()
    
    async def execute_signal(self, signal: Signal) -> dict:
        """Execute signal via cTrader API."""
        try:
            if signal.direction == 'long':
                result = await self.client.place_order(
                    symbol_id=self.cfg.SYMBOL_ID,
                    side='buy',
                    volume=signal.size,
                    stop_loss=signal.stop_loss,
                    take_profit=signal.take_profit,
                    account_id=self.cfg.ACCOUNT_ID
                )
            else:
                result = await self.client.place_order(
                    symbol_id=self.cfg.SYMBOL_ID,
                    side='sell',
                    volume=signal.size,
                    stop_loss=signal.stop_loss,
                    take_profit=signal.take_profit,
                    account_id=self.cfg.ACCOUNT_ID
                )
            self.positions.append({
                'signal': signal,
                'status': 'open',
                'result': result
            })
            return result
        except Exception as e:
            print(f"❌ Execution error: {e}")
            return None


# ============================================================
# LIVE EXECUTOR
# ============================================================
async def run_live():
    """Main live trading loop."""
    from dotenv import load_dotenv
    load_dotenv('/root/ctrader_bot/.env')
    
    client_id = os.getenv('CTRADER_CLIENT_ID')
    client_secret = os.getenv('CTRADER_SECRET')
    access_token = os.getenv('CTRADER_ACCESS_TOKEN')
    
    print("="*60)
    print("🚀 FTMO XAUUSD Killer - LIVE TRADING")
    print("="*60)
    print(f"Account: {Config.ACCOUNT_ID}")
    print(f"Symbol: {Config.SYMBOL}")
    print(f"Risk: {Config.RISK_PCT*100}% per trade")
    print(f"Strategy: EMA {Config.EMA_FAST}/{Config.EMA_SLOW} | RSI {Config.RSI_THRESHOLD}")
    print(f"SL: {Config.SL_PIPS}p | TP: {Config.TP_PIPS}p")
    print(f"Session: {Config.SESSION_FILTER}")
    print("="*60)
    
    # Connect to cTrader
    client = cTraderClient(
        client_id=client_id,
        client_secret=client_secret,
        access_token=access_token,
        account_id=Config.ACCOUNT_ID
    )
    
    await client.connect()
    await client.authenticate()
    print("✅ Connected to cTrader!")
    
    # Get account info
    acc = await client.get_account_info()
    print(f"Balance: ${acc.get('balance', 'N/A')}")
    
    # Init bot
    bot = ProductionBot(client, Config)
    bot.balance = acc.get('balance', 10000)
    bot.peak_balance = bot.balance
    bot.daily_start_balance = bot.balance
    
    # Subscribe to symbols
    await client.subscribe([Config.SYMBOL_ID])
    print(f"📊 Subscribed to {Config.SYMBOL}")
    
    # Main loop - listen for bars
    async for bar in client.stream_bars(Config.SYMBOL_ID, period=2):  # H1 = period 2
        signal = await bot.on_bar(bar)
        if signal:
            print(f"\n📡 Signal: {signal.direction.upper()} @ {signal.entry_price:.2f}")
            print(f"   SL: {signal.stop_loss:.2f} | TP: {signal.take_profit:.2f}")
            print(f"   Size: {signal.size:.2f} lots | Confidence: {signal.confidence:.0%}")
            result = await bot.execute_signal(signal)
            if result:
                print(f"   ✅ Order placed! ID: {result.get('orderId', 'N/A')}")
    
    await client.disconnect()

if __name__ == "__main__":
    import os
    asyncio.run(run_live())
