"""Backtest of btc_daytrade_model.pine / btc_daytrade_strategy.pine in Python.

Re-implements the Pine logic (Pine-style EMA/RMA seeding, Supertrend, DMI,
daily-anchored VWAP, non-repainting 1h trend) and simulates the strategy the
way TradingView's broker emulator does: orders from a signal bar fill at the
next bar's open; stop/target fill intrabar (stop assumed first if both hit).

Usage:
    python backtest_daytrade.py DATA.parquet|DATA.csv [--threshold 50] [...]

Data needs 15m (or any intraday) bars with columns:
open_time_ms (or datetime), open, high, low, close, volume (or volume_base).
"""
import argparse

import numpy as np
import pandas as pd


# ---------- Pine built-ins ----------
def pine_sma(x, n):
    return pd.Series(x).rolling(n).mean().to_numpy()


def _seeded(x, n, alpha):
    x = np.asarray(x, dtype=float)
    out = np.full(len(x), np.nan)
    start = None
    for i in range(len(x)):  # first index with n consecutive non-nan values
        if i >= n - 1 and not np.isnan(x[i - n + 1:i + 1]).any():
            start = i
            break
    if start is None:
        return out
    out[start] = x[start - n + 1:start + 1].mean()
    for i in range(start + 1, len(x)):
        v = x[i]
        out[i] = out[i - 1] if np.isnan(v) else alpha * v + (1 - alpha) * out[i - 1]
    return out


def pine_ema(x, n):
    return _seeded(x, n, 2.0 / (n + 1))


def pine_rma(x, n):
    return _seeded(x, n, 1.0 / n)


def true_range(h, l, c):
    pc = np.roll(c, 1)
    tr = np.maximum(h - l, np.maximum(np.abs(h - pc), np.abs(l - pc)))
    tr[0] = h[0] - l[0]
    return tr


def pine_rsi(c, n):
    ch = np.diff(c, prepend=np.nan)
    up = pine_rma(np.where(np.isnan(ch), np.nan, np.maximum(ch, 0)), n)
    dn = pine_rma(np.where(np.isnan(ch), np.nan, np.maximum(-ch, 0)), n)
    with np.errstate(divide="ignore", invalid="ignore"):
        rsi = np.where(dn == 0, 100.0, np.where(up == 0, 0.0, 100 - 100 / (1 + up / dn)))
    rsi[np.isnan(up) | np.isnan(dn)] = np.nan
    return rsi


def pine_supertrend(h, l, c, factor, n):
    atr = pine_rma(true_range(h, l, c), n)
    src = (h + l) / 2
    ub_raw, lb_raw = src + factor * atr, src - factor * atr
    N = len(c)
    ub, lb = np.full(N, np.nan), np.full(N, np.nan)
    st, d = np.full(N, np.nan), np.ones(N)
    for i in range(N):
        pl = 0.0 if i == 0 or np.isnan(lb[i - 1]) else lb[i - 1]
        pu = 0.0 if i == 0 or np.isnan(ub[i - 1]) else ub[i - 1]
        pc = c[i - 1] if i > 0 else np.nan
        lb[i] = lb_raw[i] if (lb_raw[i] > pl or pc < pl) else pl
        ub[i] = ub_raw[i] if (ub_raw[i] < pu or pc > pu) else pu
        if i == 0 or np.isnan(atr[i - 1]):
            d[i] = 1
        elif st[i - 1] == pu:
            d[i] = -1 if c[i] > ub[i] else 1
        else:
            d[i] = 1 if c[i] < lb[i] else -1
        st[i] = lb[i] if d[i] == -1 else ub[i]
    return st, d


def pine_adx(h, l, c, n):
    up = np.diff(h, prepend=np.nan)
    dn = -np.diff(l, prepend=np.nan)
    pdm = np.where(np.isnan(up), np.nan, np.where((up > dn) & (up > 0), up, 0.0))
    mdm = np.where(np.isnan(dn), np.nan, np.where((dn > up) & (dn > 0), dn, 0.0))
    tr = pine_rma(true_range(h, l, c), n)
    p = 100 * pine_rma(pdm, n) / tr
    m = 100 * pine_rma(mdm, n) / tr
    s = p + m
    return 100 * pine_rma(np.abs(p - m) / np.where(s == 0, 1, s), n)


# ---------- Model ----------
def compute_signals(df, P):
    o, h, l, c, v = (df[k].to_numpy(float) for k in ("open", "high", "low", "close", "volume"))
    t = df["time"]
    N = len(c)
    atr = pine_rma(true_range(h, l, c), P.atrLen)

    day = t.dt.floor("D")
    hlc3 = (h + l + c) / 3
    vwap = (pd.Series(hlc3 * v).groupby(day.values).cumsum() / pd.Series(v).groupby(day.values).cumsum()).to_numpy()
    vwapScore = np.where(~np.isnan(vwap) & (atr > 0), np.clip((c - vwap) / (0.5 * atr), -1, 1), 0.0)

    emaF, emaS = pine_ema(c, P.emaFast), pine_ema(c, P.emaSlow)
    emaScore = (np.where(c > emaF, 1.0, -1.0) + np.where(emaF > emaS, 1.0, -1.0)) / 2

    _, stDir = pine_supertrend(h, l, c, P.stFactor, P.stAtr)
    stScore = np.where(stDir < 0, 1.0, -1.0)

    rsi = pine_rsi(c, P.rsiLen)
    rsiScore = np.clip((rsi - 50) / 20, -1, 1)

    rng = h - l
    barDir = np.where(rng > 0, (c - o) / np.where(rng > 0, rng, 1), 0.0)
    volEma = pine_ema(v, P.flowLen)
    flow = pine_ema(v * barDir, P.flowLen)
    hasVol = ~np.isnan(flow) & (volEma > 0)
    flowScore = np.where(hasVol, np.clip(3 * flow / np.where(volEma > 0, volEma, 1), -1, 1), 0.0)
    volSma = pine_sma(v, P.rvolLen)
    rvol = np.where(volSma > 0, v / np.where(volSma > 0, volSma, 1), np.nan)

    # 1h trend from the last closed hour (request.security + [1] + lookahead_on)
    hr = df.set_index("time")["close"].resample(P.htf, label="left", closed="left").last().dropna()
    hE = pd.Series(pine_ema(hr.to_numpy(), P.htfLen), index=hr.index)
    hC1, hE1, hE2 = hr.shift(1), hE.shift(1), hE.shift(2)
    key = t.dt.floor(P.htf)
    htfC, htfE, htfEP = (s.reindex(key).to_numpy() for s in (hC1, hE1, hE2))
    hasHtf = ~np.isnan(htfEP)
    htfScore = np.where(hasHtf, (np.where(htfC > htfE, 1.0, -1.0) + np.where(htfE > htfEP, 1.0, -1.0)) / 2, 0.0)

    adx = pine_adx(h, l, c, P.adxLen)
    trending = adx >= P.adxMin

    wFlow = np.where(hasVol, P.wFlow, 0.0)
    wHtf = np.where(hasHtf, P.wHtf, 0.0)
    wSum = P.wVwap + P.wEma + P.wSt + P.wRsi + wFlow + wHtf
    raw = 100 * (P.wVwap * vwapScore + P.wEma * emaScore + P.wSt * stScore + P.wRsi * rsiScore
                 + wFlow * flowScore + wHtf * htfScore) / wSum
    score = pine_ema(raw, P.smooth)

    mins = (t.dt.hour * 60 + t.dt.minute).to_numpy()
    s0, s1 = P.session
    inSess = (mins >= s0) & (mins < s1)

    # ---- indicator state machine (identical to the Pine script) ----
    thr = P.threshold
    pos, stopLvl, tgtLvl, lastSig = 0, np.nan, np.nan, None
    armL = armS = True
    longSig = np.zeros(N, bool); shortSig = np.zeros(N, bool)
    exitFade = np.zeros(N, bool)
    stopArr = np.full(N, np.nan); tgtArr = np.full(N, np.nan)
    for i in range(N):
        sc = score[i]
        if np.isnan(sc):
            continue
        if sc < thr * 0.5:
            armL = True
        if sc > -thr * 0.5:
            armS = True
        okSess = (not P.useSession) or inSess[i]
        okVol = P.minRvol <= 0 or (not np.isnan(rvol[i]) and rvol[i] >= P.minRvol)
        okAdx = (not P.requireAdx) or bool(trending[i])
        cd = lastSig is None or i - lastSig >= P.cooldown
        ok = okSess and okVol and okAdx and cd
        ls = sc >= thr and ok and armL and pos != 1
        ss = sc <= -thr and ok and armS and pos != -1
        sessOver = P.useSession and not inSess[i]
        sHL = pos == 1 and l[i] <= stopLvl; tHL = pos == 1 and h[i] >= tgtLvl
        sHS = pos == -1 and h[i] >= stopLvl; tHS = pos == -1 and l[i] <= tgtLvl
        fL = pos == 1 and (sc < 0 or sessOver)
        fS = pos == -1 and (sc > 0 or sessOver)
        eL = (not ss) and (sHL or tHL or fL)
        eS = (not ls) and (sHS or tHS or fS)
        eStop = (eL and sHL) or (eS and sHS)
        eTgt = (not eStop) and ((eL and tHL) or (eS and tHS))
        exitFade[i] = (eL or eS) and not eStop and not eTgt
        if ls:
            pos, armL, lastSig = 1, False, i
            stopLvl, tgtLvl = c[i] - P.stopAtr * atr[i], c[i] + P.rr * P.stopAtr * atr[i]
        elif ss:
            pos, armS, lastSig = -1, False, i
            stopLvl, tgtLvl = c[i] + P.stopAtr * atr[i], c[i] - P.rr * P.stopAtr * atr[i]
        elif eL or eS:
            pos, stopLvl, tgtLvl = 0, np.nan, np.nan
        longSig[i], shortSig[i] = ls, ss
        stopArr[i], tgtArr[i] = stopLvl, tgtLvl
    return dict(o=o, h=h, l=l, c=c, t=t, longSig=longSig, shortSig=shortSig,
                exitFade=exitFade, stop=stopArr, tgt=tgtArr)


def simulate(S, P):
    """TradingView-style broker emulation for btc_daytrade_strategy.pine."""
    o, h, l, c, t = S["o"], S["h"], S["l"], S["c"], S["t"]
    N = len(c)
    fee = P.commission / 100
    equity = P.capital
    side, qty, entry, stp, tgt = 0, 0.0, 0.0, np.nan, np.nan
    pending = None  # ("long"/"short"/"close", stop, tgt)
    trades, eq_curve = [], np.empty(N)

    def close_pos(price, i, reason):
        nonlocal equity, side, qty
        pnl = side * qty * (price - entry) - fee * qty * price
        equity += pnl
        trades.append(dict(entry_time=entry_time, exit_time=t.iloc[i], side=side, entry=entry,
                           exit=price, pnl=pnl - entry_fee, ret=(pnl - entry_fee) / entry_equity, reason=reason))
        side, qty = 0, 0.0

    for i in range(N):
        # 1) market orders from previous bar fill at this open
        if pending is not None:
            kind, ps, pt = pending
            pending = None
            if kind == "close" and side != 0:
                close_pos(o[i], i, "fade/session")
            elif kind in ("long", "short"):
                want = 1 if kind == "long" else -1
                if side == -want:
                    close_pos(o[i], i, "reverse")
                if side == 0 or side == -want:
                    entry_equity = equity
                    entry = o[i] + want * P.slippage
                    qty = equity * P.qty_pct / 100 / entry
                    entry_fee = fee * qty * entry
                    equity -= entry_fee
                    side, entry_time = want, t.iloc[i]
                    stp, tgt = ps, pt
        # 2) stop / target intrabar
        if side == 1:
            if l[i] <= stp:
                close_pos(min(o[i], stp) - P.slippage, i, "stop")
            elif h[i] >= tgt:
                close_pos(max(o[i], tgt), i, "target")
        elif side == -1:
            if h[i] >= stp:
                close_pos(max(o[i], stp) + P.slippage, i, "stop")
            elif l[i] <= tgt:
                close_pos(min(o[i], tgt), i, "target")
        # 3) orders generated at this bar's close
        if S["longSig"][i]:
            pending = ("long", S["stop"][i], S["tgt"][i])
        elif S["shortSig"][i]:
            if P.allowShorts:
                pending = ("short", S["stop"][i], S["tgt"][i])
            elif side == 1:
                pending = ("close", np.nan, np.nan)
        elif S["exitFade"][i] and side != 0:
            pending = ("close", np.nan, np.nan)
        eq_curve[i] = equity + (side * qty * (c[i] - entry) if side else 0.0)
    return pd.DataFrame(trades), pd.Series(eq_curve, index=t.values)


def report(trades, eq, df, P, label=""):
    if trades.empty:
        print(f"{label}: no trades")
        return {}
    wins = trades.pnl > 0
    gp, gl = trades.pnl[wins].sum(), -trades.pnl[~wins].sum()
    dd = (eq / eq.cummax() - 1).min()
    years = (df.time.iloc[-1] - df.time.iloc[0]).days / 365.25
    net = eq.iloc[-1] / P.capital - 1
    bh = df.close.iloc[-1] / df.close.iloc[0] - 1
    r = dict(label=label, trades=len(trades), trades_per_day=len(trades) / (years * 365.25),
             win_rate=wins.mean(), profit_factor=gp / gl if gl else np.inf,
             net_return=net, cagr=(1 + net) ** (1 / years) - 1 if net > -1 else -1.0,
             max_dd=dd, avg_trade=trades.ret.mean(), buy_hold=bh)
    return r


def load(path):
    df = pd.read_parquet(path) if path.endswith(".parquet") else pd.read_csv(path)
    if "open_time_ms" in df:
        df["time"] = pd.to_datetime(df.open_time_ms, unit="ms")
    else:
        df["time"] = pd.to_datetime(df["datetime"])
    if "volume" not in df:
        df["volume"] = df["volume_base"]
    return df[["time", "open", "high", "low", "close", "volume"]].sort_values("time").reset_index(drop=True)


def params(**over):
    P = argparse.Namespace(
        emaFast=9, emaSlow=21, stFactor=2.0, stAtr=10, htf="1h", htfLen=50,
        rsiLen=9, flowLen=14, rvolLen=20, adxLen=14, adxMin=18.0,
        wVwap=2.0, wEma=1.5, wSt=1.0, wRsi=1.0, wFlow=1.0, wHtf=1.5,
        useSession=True, session=(8 * 60, 21 * 60), requireAdx=True, minRvol=1.0, cooldown=5,
        atrLen=14, stopAtr=1.5, rr=2.0, smooth=2, threshold=50.0,
        capital=10000.0, qty_pct=100.0, commission=0.05, slippage=0.2, allowShorts=True)
    for k, v in over.items():
        setattr(P, k, v)
    return P


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("data")
    ap.add_argument("--threshold", type=float, default=50.0)
    ap.add_argument("--commission", type=float, default=0.05)
    ap.add_argument("--no-shorts", action="store_true")
    a = ap.parse_args()
    df = load(a.data)
    P = params(threshold=a.threshold, commission=a.commission, allowShorts=not a.no_shorts)
    S = compute_signals(df, P)
    tr, eq = simulate(S, P)
    for k, v in report(tr, eq, df, P, "default").items():
        print(f"{k:>16}: {v:.4f}" if isinstance(v, float) else f"{k:>16}: {v}")
