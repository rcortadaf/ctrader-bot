# cTrader Bot Engine �印记

Autonomous trading bot framework for cTrader using the Open API (WebSocket).

## Strategy Battery (FTMO 1-Step Challenge Ready)

| Bot | Strategy | Status |
|-----|----------|--------|
| `trend_catcher` | EMA 8/21 Crossover + RSI | ✅ Backtested |
| `breakout_hunter` | Range Breakout + Volume | 🔨 In progress |
| `smart_money` | Orderflow + Smart Money | 🔜 Next |

**Target:** XAUUSD | **Timeframe:** H1 | **Broker:** FTMO / IC Markets

## Project Structure

```
ctrader_bot/
├── bots/              # Strategy implementations
│   └── trend_catcher/
├── lib/               # Core engine
│   ├── ctrader_client.py
│   └── backtester.py
├── data/              # Historical data (not committed)
├── backtests/         # Backtest results
└── config/            # Configuration
```

## Setup

```bash
git clone https://github.com/rcortadaf/ctrader-bot.git
cd ctrader-bot
cp .env.example .env
# Fill in your cTrader API credentials in .env
pip install websockets python-dotenv
```

## Run Backtest

```bash
cd ctrader_bot
python -c "
import json
from lib.backtester import Backtester
from bots.trend_catcher.bot import TrendCatcherBot
with open('data/xauusd_h1_6m.json') as f:
    data = json.load(f)
bt = Backtester(TrendCatcherBot(), data)
results = bt.run()
bt.print_report()
"
```

## Credentials

Obtain cTrader API credentials at https://openapi.ctrader.com/apps

## Risk Management (FTMO Rules)

- Max Daily Loss: 3%
- Max Total Loss: 10%
- Profit Target: 10%
- Best Day Rule: 50% max contribution
