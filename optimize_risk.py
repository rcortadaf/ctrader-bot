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

def calc_ema_fast(close_arr, period, idx):
    if idx < period - 1:
        return close_arr[idx]
    mult = 2 / (period + 1)
    window = close_arr[idx - period + 1:idx + 1]
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
        if d > 0: gains += d
        else: losses -= d
    if losses == 0:
        return 100
    return 100 - 100 / (1 + gains / losses)

def bt(fast, slow, rsi_th, sl_pips, tp_pips, risk_pct, max_daily_dd=0.03, max_total_dd=0.10):
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
    daily_loss_streak = 0
    trading_enabled = True

    for i in range(min_start, len(bars)):
        now_date = bars[i]['timestamp'].date()
        if now_date != last_date:
            daily_start = balance
            last_date = now_date
            daily_loss_streak = 0

        fast_ema = calc_ema_fast(closes, fast, i)
        slow_ema = calc_ema_fast(closes, slow, i)
        prev_fast = calc_ema_fast(closes, fast, i-1)
        prev_slow = calc_ema_fast(closes, slow, i-1)
        rsi = calc_rsi_fast(closes, i, rsi_per)

        if trade is None and trading_enabled:
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
                trades.append({'pnl': pnl, 'type': 'SL' if hit_sl else 'TP', 'dir': trade['dir']})
                trade = None
                if pnl < 0:
                    daily_loss_streak += 1
                    if daily_loss_streak >= 2:
                        trading_enabled = False

        if balance > peak:
            peak = balance
        dd = peak - balance
        if dd > max_dd:
            max_dd = dd
        if (daily_start - balance) / daily_start > max_daily_dd:
            break
        if (10000 - balance) / 10000 > max_total_dd:
            break

    wins = [t for t in trades if t['pnl'] > 0]
    losses = [t for t in trades if t['pnl'] <= 0]
    net = balance - 10000
    wr = len(wins) / len(trades) * 100 if trades else 0
    loss_sum = sum(abs(t['pnl']) for t in losses)
    pf = sum(t['pnl'] for t in wins) / loss_sum if loss_sum > 0 else 0
    return {
        'net': net/100, 'wr': wr, 'pf': pf, 'trades': len(trades),
        'dd': max_dd/100, 'wins': len(wins), 'losses': len(losses),
        'f': fast, 's': slow, 'rsi': rsi_th, 'sl': sl_pips, 'tp': tp_pips, 'risk': risk_pct,
        'sl_hits': len([t for t in trades if t['type'] == 'SL']),
        'tp_hits': len([t for t in trades if t['type'] == 'TP'])
    }

# Test best configs with 1% risk
configs_2pct = [
    (8, 21, 50, 40, 80, 0.02),  # Best: +13.97% DD 12.1%
    (8, 30, 50, 50, 150, 0.02),  # +9.86% DD 4.5%
    (8, 21, 55, 40, 80, 0.02),  # +5.25% DD 16%
]
configs_1pct = [
    (8, 21, 50, 40, 80, 0.01),
    (8, 30, 50, 50, 150, 0.01),
    (8, 21, 55, 40, 80, 0.01),
    (8, 21, 50, 50, 100, 0.01),
]
configs_15pct = [
    (8, 21, 50, 40, 80, 0.015),
    (8, 30, 50, 50, 150, 0.015),
]

print("Testing 2% risk configs:")
results = []
for cfg in configs_2pct:
    r = bt(*cfg)
    results.append(r)
    print("  EMA=" + str(r['f']) + "/" + str(r['s']) + " SL=" + str(r['sl']) + "p TP=" + str(r['tp']) + "p Risk=" + str(r['risk']*100) + "% -> Net: " + ("%.2f%%" % r['net']) + " DD: " + ("%.1f%%" % r['dd']) + " WR: " + ("%.1f%%" % r['wr']) + " PF: " + ("%.2f" % r['pf']) + " Trades: " + str(r['trades']))

print("\nTesting 1.5% risk configs:")
for cfg in configs_15pct:
    r = bt(*cfg)
    results.append(r)
    print("  EMA=" + str(r['f']) + "/" + str(r['s']) + " SL=" + str(r['sl']) + "p TP=" + str(r['tp']) + "p Risk=" + str(r['risk']*100) + "% -> Net: " + ("%.2f%%" % r['net']) + " DD: " + ("%.1f%%" % r['dd']) + " WR: " + ("%.1f%%" % r['wr']) + " PF: " + ("%.2f" % r['pf']) + " Trades: " + str(r['trades']))

print("\nTesting 1% risk configs:")
for cfg in configs_1pct:
    r = bt(*cfg)
    results.append(r)
    print("  EMA=" + str(r['f']) + "/" + str(r['s']) + " SL=" + str(r['sl']) + "p TP=" + str(r['tp']) + "p Risk=" + str(r['risk']*100) + "% -> Net: " + ("%.2f%%" % r['net']) + " DD: " + ("%.1f%%" % r['dd']) + " WR: " + ("%.1f%%" % r['wr']) + " PF: " + ("%.2f" % r['pf']) + " Trades: " + str(r['trades']))

# FTMO filtering
ftmo_ok = [r for r in results if r['dd'] <= 0.105]  # max 10.5% (margin)
ftmo_ok.sort(key=lambda x: x['net'], reverse=True)

print("\n" + "="*70)
print("FTMO-COMPLIANT CONFIGS (DD <= 10.5%):")
print("="*70)
for r in ftmo_ok:
    print("  EMA=" + str(r['f']) + "/" + str(r['s']) + " RSI=" + str(r['rsi']) + " SL=" + str(r['sl']) + "p TP=" + str(r['tp']) + "p Risk=" + str(r['risk']*100) + "% -> Net: " + ("%.2f%%" % r['net']) + " DD: " + ("%.1f%%" % r['dd']) + " PF: " + ("%.2f" % r['pf']) + " Trades: " + str(r['trades']))

with open('/root/ctrader_bot/backtests/trend_catcher_ftmo_check.json', 'w') as f:
    json.dump({'all_results': results, 'ftmo_compliant': ftmo_ok}, f, indent=2, default=str)
print("\nSaved!")
