import json
from datetime import datetime

with open('/root/ctrader_bot/data/xauusd_h1_6m.json', 'r') as f:
    bars_data = json.load(f)

bars = []
for bar in bars_data:
    low = bar.get('low', 0) / 1000.0
    bars.append({
        'timestamp': datetime.utcfromtimestamp(bar.get('utcTimestampInMinutes', 0) * 60),
        'open': low + bar.get('deltaOpen', 0) / 1000.0,
        'high': low + bar.get('deltaHigh', 0) / 1000.0,
        'low': low,
        'close': low + bar.get('deltaClose', 0) / 1000.0,
        'volume': bar.get('volume', 0)
    })

def calc_ema(values, period):
    if len(values) < period:
        return values[-1] if values else 0
    mult = 2 / (period + 1)
    ema = sum(values[:period]) / period
    for v in values[period:]:
        ema = (v - ema) * mult + ema
    return ema

def calc_rsi(prices, period=14):
    if len(prices) < period + 1:
        return 50
    gains = [max(prices[i]-prices[i-1], 0) for i in range(1, len(prices))]
    losses = [max(prices[i-1]-prices[i], 0) for i in range(1, len(prices))]
    ag = sum(gains[-period:]) / period
    al = sum(losses[-period:]) / period
    if al == 0:
        return 100
    return 100 - 100/(1 + ag/al)

def backtest_fast(fast_ema, slow_ema, rsi_th, sl_pips, tp_pips, risk_pct):
    balance = 10000
    peak = balance
    max_dd = 0
    trades = []
    trade = None
    daily_start = balance
    last_date = bars[0]['timestamp'].date()
    good_hours = [12, 13, 14, 18, 19]
    rsi_period = 14
    min_start = slow_ema + rsi_period + 5

    for i in range(min_start, len(bars)):
        now_date = bars[i]['timestamp'].date()
        if now_date != last_date:
            daily_start = balance
            last_date = now_date

        c = [bars[j]['close'] for j in range(i-150, i+1)]
        if len(c) < min_start:
            continue

        fast = calc_ema(c, fast_ema)
        slow = calc_ema(c, slow_ema)
        rsi = calc_rsi(c, rsi_period)

        if trade is None:
            prev_fast = calc_ema(c[:-1], fast_ema)
            prev_slow = calc_ema(c[:-1], slow_ema)
            hour = bars[i]['timestamp'].hour

            if prev_fast <= prev_slow and fast > slow and rsi > rsi_th and hour in good_hours:
                sl = sl_pips * 0.01
                size = balance * risk_pct / sl
                trade = {'entry': bars[i]['close'], 'sl': bars[i]['close'] - sl,
                         'tp': bars[i]['close'] + tp_pips * 0.01, 'dir': 'long', 'size': size}
            elif prev_fast >= prev_slow and fast < slow and rsi < (100 - rsi_th) and hour in good_hours:
                sl = sl_pips * 0.01
                size = balance * risk_pct / sl
                trade = {'entry': bars[i]['close'], 'sl': bars[i]['close'] + sl,
                         'tp': bars[i]['close'] - tp_pips * 0.01, 'dir': 'short', 'size': size}

        if trade:
            b = bars[i]
            if trade['dir'] == 'long':
                if b['low'] <= trade['sl']:
                    balance += (trade['sl'] - trade['entry']) * trade['size']
                    trades.append({'pnl': (trade['sl'] - trade['entry']) * trade['size']})
                    trade = None
                elif b['high'] >= trade['tp']:
                    balance += (trade['tp'] - trade['entry']) * trade['size']
                    trades.append({'pnl': (trade['tp'] - trade['entry']) * trade['size']})
                    trade = None
            else:
                if b['high'] >= trade['sl']:
                    balance += (trade['entry'] - trade['sl']) * trade['size']
                    trades.append({'pnl': (trade['entry'] - trade['sl']) * trade['size']})
                    trade = None
                elif b['low'] <= trade['tp']:
                    balance += (trade['entry'] - trade['tp']) * trade['size']
                    trades.append({'pnl': (trade['entry'] - trade['tp']) * trade['size']})
                    trade = None

        peak = max(peak, balance)
        dd = peak - balance
        if dd > max_dd:
            max_dd = dd
        if (daily_start - balance) / daily_start > 0.03:
            break
        if (10000 - balance) / 10000 > 0.10:
            break

    wins = [t for t in trades if t['pnl'] > 0]
    losses = [t for t in trades if t['pnl'] <= 0]
    net = balance - 10000
    wr = len(wins)/len(trades)*100 if trades else 0
    pf = abs(sum(t['pnl'] for t in wins)/sum(t['pnl'] for t in losses)) if losses and sum(t['pnl'] for t in losses) != 0 else 0
    return {'net_pct': net/100, 'wr': wr, 'pf': pf, 'trades': len(trades),
            'max_dd_pct': max_dd/100, 'wins': len(wins), 'losses': len(losses),
            'fast': fast_ema, 'slow': slow_ema, 'rsi_th': rsi_th, 'sl': sl_pips, 'tp': tp_pips, 'risk': risk_pct}

configs = []
for fast in [5, 8, 10, 12]:
    for slow in [21, 25, 30]:
        if slow <= fast:
            continue
        for rsi_th in [50, 55]:
            for sl in [40, 50, 60]:
                for tp in [80, 100, 120, 150]:
                    for risk in [0.02, 0.025]:
                        configs.append((fast, slow, rsi_th, sl, tp, risk))

print("Testing " + str(len(configs)) + " configurations...")
results = []
best = None

for idx, cfg in enumerate(configs):
    f, s, rsi, sl, tp, risk = cfg
    res = backtest_fast(f, s, rsi, sl, tp, risk)
    results.append(res)
    if best is None or res['net_pct'] > best['net_pct']:
        best = res
    if idx % 100 == 0:
        best_txt = ("%.2f%%" % best['net_pct']) if best else 'none'
        print(str(idx) + "/" + str(len(configs)) + " - current best: " + best_txt)

results.sort(key=lambda x: x['net_pct'], reverse=True)
print("\nTOP 5 OPTIMIZED TREND CATCHER:")
for i, r in enumerate(results[:5]):
    print(str(i+1) + ". EMA=" + str(r['fast']) + "/" + str(r['slow']) + " RSI=" + str(r['rsi_th']) + " SL=" + str(r['sl']) + "p TP=" + str(r['tp']) + "p Risk=" + str(r['risk']*100) + "%")
    print("   Net: " + ("%.2f%%" % r['net_pct']) + " WR: " + ("%.1f%%" % r['wr']) + " PF: " + ("%.2f" % r['pf']) + " Trades: " + str(r['trades']) + " DD: " + ("%.1f%%" % r['max_dd_pct']))

with open('/root/ctrader_bot/backtests/trend_catcher_optimized_results.json', 'w') as f:
    json.dump({'best_config': best, 'top_10': results[:10]}, f, indent=2)
print("\nBest config saved!")
print("Net=" + ("%.2f%%" % best['net_pct']) + " WR=" + ("%.1f%%" % best['wr']) + " PF=" + ("%.2f" % best['pf']) + " Trades=" + str(best['trades']) + " DD=" + ("%.1f%%" % best['max_dd_pct']))
