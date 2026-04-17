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
closes = [b['close'] for b in bars]

def calc_ema_fast(close_arr, period, start_idx):
    if start_idx < period - 1:
        return close_arr[start_idx]
    mult = 2 / (period + 1)
    window = close_arr[start_idx - period + 1:start_idx + 1]
    ema = sum(window) / period
    for j in range(period, len(window)):
        ema = (window[j] - ema) * mult + ema
    return ema

def calc_rsi_fast(close_arr, idx, period=14):
    if idx < period:
        return 50
    gains = 0
    losses = 0
    for j in range(idx - period + 1, idx):
        d = close_arr[j+1] - close_arr[j]
        if d > 0:
            gains += d
        else:
            losses -= d
    if losses == 0:
        return 100
    return 100 - 100 / (1 + gains / losses)

def bt(fast, slow, rsi_th, sl_pips, tp_pips, risk_pct):
    balance = 10000
    peak = 10000
    max_dd = 0
    trades = []
    trade = None
    daily_start = 10000
    last_date = bars[0]['timestamp'].date()
    good_hours = [12, 13, 14, 18, 19]
    rsi_per = 14
    min_start = slow + rsi_per + 5

    for i in range(min_start, len(bars)):
        now_date = bars[i]['timestamp'].date()
        if now_date != last_date:
            daily_start = balance
            last_date = now_date

        fast_ema = calc_ema_fast(closes, fast, i)
        slow_ema = calc_ema_fast(closes, slow, i)
        prev_fast = calc_ema_fast(closes, fast, i-1)
        prev_slow = calc_ema_fast(closes, slow, i-1)
        rsi = calc_rsi_fast(closes, i, rsi_per)

        if trade is None:
            hour = bars[i]['timestamp'].hour
            ep = closes[i]

            if prev_fast <= prev_slow and fast_ema > slow_ema and rsi > rsi_th and hour in good_hours:
                sl = sl_pips * 0.01
                size = balance * risk_pct / sl
                trade = {'entry': ep, 'sl': ep - sl, 'tp': ep + tp_pips*0.01, 'dir': 1, 'size': size}
            elif prev_fast >= prev_slow and fast_ema < slow_ema and rsi < (100 - rsi_th) and hour in good_hours:
                sl = sl_pips * 0.01
                size = balance * risk_pct / sl
                trade = {'entry': ep, 'sl': ep + sl, 'tp': ep - tp_pips*0.01, 'dir': -1, 'size': size}

        if trade:
            b = bars[i]
            hit_sl = (trade['dir'] == 1 and b['low'] <= trade['sl']) or (trade['dir'] == -1 and b['high'] >= trade['sl'])
            hit_tp = (trade['dir'] == 1 and b['high'] >= trade['tp']) or (trade['dir'] == -1 and b['low'] <= trade['tp'])
            if hit_sl or hit_tp:
                price = trade['sl'] if hit_sl else trade['tp']
                pnl = (trade['entry'] - price) * trade['size'] if trade['dir'] == -1 else (price - trade['entry']) * trade['size']
                balance += pnl
                trades.append({'pnl': pnl})
                trade = None

        if balance > peak:
            peak = balance
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
    wr = len(wins) / len(trades) * 100 if trades else 0
    loss_sum = sum(t['pnl'] for t in losses)
    pf = abs(sum(t['pnl'] for t in wins) / loss_sum) if losses and loss_sum != 0 else 0
    return {
        'net': net/100, 'wr': wr, 'pf': pf, 'trades': len(trades),
        'dd': max_dd/100, 'wins': len(wins), 'losses': len(losses),
        'f': fast, 's': slow, 'rsi': rsi_th, 'sl': sl_pips, 'tp': tp_pips, 'risk': risk_pct
    }

configs = [
    (8, 21, 50, 40, 80, 0.02), (8, 21, 50, 50, 100, 0.02), (8, 21, 50, 50, 150, 0.02),
    (8, 21, 50, 60, 120, 0.02), (8, 25, 50, 50, 100, 0.02),
    (5, 21, 50, 40, 80, 0.02), (5, 21, 50, 50, 100, 0.025),
    (10, 25, 50, 50, 100, 0.02), (10, 25, 50, 50, 125, 0.025),
    (12, 30, 50, 50, 100, 0.02), (12, 30, 50, 60, 120, 0.02),
    (8, 21, 55, 40, 80, 0.02), (8, 21, 55, 50, 100, 0.02),
    (5, 15, 50, 40, 80, 0.02), (5, 15, 50, 50, 100, 0.02),
    (8, 30, 50, 50, 100, 0.02), (8, 30, 50, 50, 150, 0.02),
    (5, 25, 50, 40, 80, 0.02), (10, 21, 50, 50, 100, 0.02),
]

results = []
best = None
for cfg in configs:
    res = bt(*cfg)
    results.append(res)
    if best is None or res['net'] > best['net']:
        best = res

results.sort(key=lambda x: x['net'], reverse=True)
print("TREND CATCHER OPTIMIZED:")
for i, r in enumerate(results):
    print(str(i+1) + ". EMA=" + str(r['f']) + "/" + str(r['s']) + " RSI=" + str(r['rsi']) + " SL=" + str(r['sl']) + "p TP=" + str(r['tp']) + "p Risk=" + str(r['risk']*100) + "% -> Net: " + ("%.2f%%" % r['net']) + " WR: " + ("%.1f%%" % r['wr']) + " PF: " + ("%.2f" % r['pf']) + " Trades: " + str(r['trades']) + " DD: " + ("%.1f%%" % r['dd']))

with open('/root/ctrader_bot/backtests/trend_catcher_optimized_results.json', 'w') as f:
    json.dump({'best_config': best, 'all_results': results}, f, indent=2, default=str)
total_trades = best['wins'] + best['losses']
print("\nBEST: Net=" + ("%.2f%%" % best['net']) + " WR=" + ("%.1f%%" % best['wr']) + " PF=" + ("%.2f" % best['pf']) + " Trades=" + str(total_trades))
