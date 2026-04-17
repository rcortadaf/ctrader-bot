"""
Backtesting engine per a bots de cTrader
Suporta: XAUUSD, múltiples Timeframes, gestió de risc FTMO-compatible
"""

import json
import csv
import os
from datetime import datetime
from typing import List, Dict, Optional, Callable
from dataclasses import dataclass, field

@dataclass
class Bar:
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float

@dataclass
class Trade:
    entry_time: datetime
    entry_price: float
    direction: str  # 'long' or 'short'
    size: float
    stop_loss: float
    take_profit: float
    exit_time: Optional[datetime] = None
    exit_price: Optional[float] = None
    pnl: Optional[float] = None
    pnl_pct: Optional[float] = None

@dataclass
class BacktestResult:
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate: float = 0.0
    total_pnl: float = 0.0
    total_pnl_pct: float = 0.0
    max_drawdown: float = 0.0
    max_drawdown_pct: float = 0.0
    sharpe_ratio: float = 0.0
    profit_factor: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    best_trade: float = 0.0
    worst_trade: float = 0.0
    trades: List[Trade] = field(default_factory=list)
    equity_curve: List[float] = field(default_factory=list)
    daily_returns: List[float] = field(default_factory=list)

class Backtester:
    def __init__(self, initial_balance: float = 10000, max_daily_loss_pct: float = 0.03,
                 max_total_loss_pct: float = 0.10):
        self.initial_balance = initial_balance
        self.balance = initial_balance
        self.max_daily_loss_pct = max_daily_loss_pct
        self.max_total_loss_pct = max_total_loss_pct
        
        self.bars: List[Bar] = []
        self.trades: List[Trade] = []
        self.equity = [initial_balance]
        
        # FTMO limits
        self.daily_start_balance = initial_balance
        self.max_total_loss = initial_balance * max_total_loss_pct
        
    def load_from_csv(self, filepath: str):
        """Load bars from CSV file"""
        self.bars = []
        with open(filepath, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                self.bars.append(Bar(
                    timestamp=datetime.fromisoformat(row['timestamp']),
                    open=float(row['open']),
                    high=float(row['high']),
                    low=float(row['low']),
                    close=float(row['close']),
                    volume=float(row.get('volume', 0))
                ))
        print(f"Loaded {len(self.bars)} bars from {filepath}")
    
    def load_from_json_bars(self, bars_data: List[dict]):
        """Load bars from parsed cTrader JSON data"""
        self.bars = []
        for bar in bars_data:
            low = bar.get('low', 0) / 1000.0
            delta_open = bar.get('deltaOpen', 0) / 1000.0
            delta_close = bar.get('deltaClose', 0) / 1000.0
            delta_high = bar.get('deltaHigh', 0) / 1000.0
            ts_min = bar.get('utcTimestampInMinutes', 0)
            
            self.bars.append(Bar(
                timestamp=datetime.utcfromtimestamp(ts_min * 60),
                open=low + delta_open,
                high=low + delta_high,
                low=low,
                close=low + delta_close,
                volume=bar.get('volume', 0)
            ))
        print(f"Loaded {len(self.bars)} bars from cTrader data")
    
    def add_indicator(self, name: str, func: Callable[['Backtester', Bar], float]):
        """Register a custom indicator function"""
        setattr(self, f"ind_{name}", func)
    
    def run(self, strategy_func: Callable[['Backtester', int], Optional[Dict]],
            symbol: str = "XAUUSD", timeframe: str = "H1") -> BacktestResult:
        """
        Run backtest with a strategy function.
        Strategy function receives (backtester, bar_index) and returns:
        - None: no action
        - Dict with: direction ('long'/'short'), size (optional), sl_pips, tp_pips
        """
        self.trades = []
        self.balance = self.initial_balance
        self.equity = [self.initial_balance]
        
        daily_pnl = 0.0
        current_trade: Optional[Trade] = None
        
        print(f"\nRunning backtest: {symbol} {timeframe}")
        print(f"Initial balance: ${self.balance:,.2f}")
        print(f"Max daily loss: {self.max_daily_loss_pct*100}%")
        print(f"Max total loss: {self.max_total_loss_pct*100}%")
        print(f"Bars: {len(self.bars)}")
        print("-" * 60)
        
        for i, bar in enumerate(self.bars):
            # Check if we need to close daily
            if i > 0 and bar.timestamp.date() != self.bars[i-1].timestamp.date():
                # New day - reset daily loss counter
                daily_pnl = 0.0
                self.daily_start_balance = self.balance
            
            # Update open trade P&L
            if current_trade:
                if current_trade.direction == 'long':
                    pnl = (bar.close - current_trade.entry_price) * current_trade.size
                else:
                    pnl = (current_trade.entry_price - bar.close) * current_trade.size
                
                # Check SL/TP
                hit = False
                exit_price = None
                
                if current_trade.direction == 'long':
                    if bar.low <= current_trade.stop_loss:
                        exit_price = current_trade.stop_loss
                        hit = True
                    elif bar.high >= current_trade.take_profit:
                        exit_price = current_trade.take_profit
                        hit = True
                else:
                    if bar.high >= current_trade.stop_loss:
                        exit_price = current_trade.stop_loss
                        hit = True
                    elif bar.low <= current_trade.take_profit:
                        exit_price = current_trade.take_profit
                        hit = True
                
                if hit:
                    current_trade.exit_time = bar.timestamp
                    current_trade.exit_price = exit_price
                    current_trade.pnl = pnl
                    current_trade.pnl_pct = pnl / self.balance * 100
                    self.trades.append(current_trade)
                    self.balance += pnl
                    daily_pnl += pnl
                    current_trade = None
            
            # Call strategy
            if not current_trade:
                signal = strategy_func(self, i)
                if signal:
                    sl_pips = signal.get('sl_pips', 50)
                    tp_pips = signal.get('tp_pips', 100)
                    direction = signal['direction']
                    size = signal.get('size', self.balance * 0.02 / (sl_pips * 0.01))  # 2% risk
                    
                    entry_price = bar.close
                    if direction == 'long':
                        stop_loss = entry_price - sl_pips * 0.01
                        take_profit = entry_price + tp_pips * 0.01
                    else:
                        stop_loss = entry_price + sl_pips * 0.01
                        take_profit = entry_price - tp_pips * 0.01
                    
                    current_trade = Trade(
                        entry_time=bar.timestamp,
                        entry_price=entry_price,
                        direction=direction,
                        size=size,
                        stop_loss=stop_loss,
                        take_profit=take_profit
                    )
            
            # Track equity
            self.equity.append(self.balance)
            
            # Check FTMO loss limits
            daily_loss = (self.daily_start_balance - self.balance) / self.daily_start_balance
            total_loss = (self.initial_balance - self.balance) / self.initial_balance
            
            if daily_loss > self.max_daily_loss_pct:
                print(f"[DAY {bar.timestamp.date()}] Daily loss limit hit: {daily_loss*100:.2f}%")
                break
            if total_loss > self.max_total_loss_pct:
                print(f"[{bar.timestamp}] Total loss limit hit: {total_loss*100:.2f}%")
                break
        
        # Close any open trade at end
        if current_trade:
            last_bar = self.bars[-1]
            if current_trade.direction == 'long':
                pnl = (last_bar.close - current_trade.entry_price) * current_trade.size
            else:
                pnl = (current_trade.entry_price - last_bar.close) * current_trade.size
            current_trade.exit_time = last_bar.timestamp
            current_trade.exit_price = last_bar.close
            current_trade.pnl = pnl
            current_trade.pnl_pct = pnl / self.balance * 100
            self.trades.append(current_trade)
            self.balance += pnl
        
        return self._calculate_results(symbol, timeframe)
    
    def _calculate_results(self, symbol: str, timeframe: str) -> BacktestResult:
        result = BacktestResult()
        result.total_trades = len(self.trades)
        
        if not self.trades:
            return result
        
        wins = [t for t in self.trades if t.pnl and t.pnl > 0]
        losses = [t for t in self.trades if t.pnl and t.pnl <= 0]
        
        result.winning_trades = len(wins)
        result.losing_trades = len(losses)
        result.win_rate = len(wins) / len(self.trades) * 100 if self.trades else 0
        
        total_pnl = sum(t.pnl for t in self.trades if t.pnl)
        result.total_pnl = total_pnl
        result.total_pnl_pct = total_pnl / self.initial_balance * 100
        
        result.avg_win = sum(t.pnl for t in wins) / len(wins) if wins else 0
        result.avg_loss = sum(t.pnl for t in losses) / len(losses) if losses else 0
        
        result.profit_factor = abs(sum(t.pnl for t in wins) / sum(t.pnl for t in losses)) if losses and sum(t.pnl for t in losses) != 0 else 0
        
        result.best_trade = max(t.pnl for t in self.trades if t.pnl) if self.trades else 0
        result.worst_trade = min(t.pnl for t in self.trades if t.pnl) if self.trades else 0
        
        # Max drawdown
        peak = self.initial_balance
        max_dd = 0
        for e in self.equity:
            if e > peak:
                peak = e
            dd = peak - e
            if dd > max_dd:
                max_dd = dd
        
        result.max_drawdown = max_dd
        result.max_drawdown_pct = max_dd / self.initial_balance * 100
        
        result.trades = self.trades
        result.equity_curve = self.equity
        
        # Print summary
        print(f"\n{'='*60}")
        print(f"BACKTEST RESULTS: {symbol} {timeframe}")
        print(f"{'='*60}")
        print(f"Period: {self.bars[0].timestamp.date()} to {self.bars[-1].timestamp.date()}")
        print(f"Total trades: {result.total_trades}")
        print(f"Win rate: {result.win_rate:.1f}%")
        print(f"Profit factor: {result.profit_factor:.2f}")
        print(f"Total P&L: ${result.total_pnl:,.2f} ({result.total_pnl_pct:+.1f}%)")
        print(f"Max drawdown: ${result.max_drawdown:,.2f} ({result.max_drawdown_pct:.1f}%)")
        print(f"Best trade: ${result.best_trade:,.2f}")
        print(f"Worst trade: ${result.worst_trade:,.2f}")
        print(f"Avg win: ${result.avg_win:,.2f} | Avg loss: ${result.avg_loss:,.2f}")
        print(f"Final balance: ${self.balance:,.2f}")
        print(f"{'='*60}")
        
        return result
    
    def save_results(self, result: BacktestResult, filename: str):
        """Save backtest results to JSON"""
        data = {
            'summary': {
                'total_trades': result.total_trades,
                'winning_trades': result.winning_trades,
                'losing_trades': result.losing_trades,
                'win_rate': result.win_rate,
                'total_pnl': result.total_pnl,
                'total_pnl_pct': result.total_pnl_pct,
                'max_drawdown': result.max_drawdown,
                'max_drawdown_pct': result.max_drawdown_pct,
                'profit_factor': result.profit_factor,
                'sharpe_ratio': result.sharpe_ratio,
                'best_trade': result.best_trade,
                'worst_trade': result.worst_trade,
            },
            'trades': [
                {
                    'entry_time': t.entry_time.isoformat(),
                    'exit_time': t.exit_time.isoformat() if t.exit_time else None,
                    'direction': t.direction,
                    'entry_price': t.entry_price,
                    'exit_price': t.exit_price,
                    'pnl': t.pnl,
                    'pnl_pct': t.pnl_pct,
                } for t in result.trades
            ]
        }
        
        with open(filename, 'w') as f:
            json.dump(data, f, indent=2)
        print(f"Results saved to {filename}")
