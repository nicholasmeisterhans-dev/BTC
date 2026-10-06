# BTC Direction Model (TradingView / Pine Script v6)

| File | What it is |
|---|---|
| `btc_direction_model.pine` | The indicator: bias score, UP/DOWN signals, dashboard, alerts |
| `btc_direction_strategy.pine` | The same logic as a strategy, so you can backtest it in the Strategy Tester |
| `btc_daytrade_model.pine` | **Day trading** indicator for 1m–15m charts (see below) |
| `btc_daytrade_strategy.pine` | Backtest version of the day trading model |

## Install
1. In TradingView, open a BTC chart (e.g. `BINANCE:BTCUSDT` or `COINBASE:BTCUSD`) on 1h, 4h or 1D.
2. Open **Pine Editor**, paste the file contents, click **Save** then **Add to chart**.
3. For alerts: **Alerts → Create alert → Condition: BTC Direction Model → "BTC-DM bullish/bearish signal"**, trigger *Once per bar close*.

## How it works
Six factors each vote from -1 (bearish) to +1 (bullish), weighted into a score from -100 to +100:

| Factor | Bullish when |
|---|---|
| EMA stack (21/55/200) | price > 21 > 55 > 200 |
| Supertrend (3, 10) | in uptrend |
| RSI (14) | above 50 (scaled, full vote at 70) |
| MACD (12/26/9) | histogram positive and rising, MACD > 0 |
| OBV vs 20 EMA | volume flow rising |
| Higher timeframe (default 1D, 50 EMA) | HTF close above a rising EMA |

- **Score ≥ +40** → bullish bias (green background, `UP` label on entry).
- **Score ≤ -40** → bearish bias (red background, `DOWN` label).
- Grey `x` → the bias faded back past zero.
- With *Only signal when ADX shows a trend* on, no new signals fire while ADX < 20 (choppy market).

The higher-timeframe data uses the last **closed** HTF bar, so it doesn't repaint. Signals on the
current bar can still change until that bar closes, so act on closed bars.

## Tuning
All lengths, weights and the threshold are inputs. Use the strategy file to check settings
on your timeframe before trusting them. Defaults include 0.1% commission and are set to
100% of equity per trade, with an optional 2.5×ATR stop.

> No indicator can tell you where BTC will go. This one tells you which way trend, momentum
> and volume currently lean. Treat it as a filter, size positions sensibly, and not as financial advice.

---

# BTC Day Trading Model (`btc_daytrade_model.pine`)

Built for **5m–15m charts** (works on 1m–30m). Paste it into the Pine Editor the same way:
clear the editor first (Ctrl+A, Delete), then paste.

## Factors (score -100 … +100)
| Factor | Bullish when | Weight |
|---|---|---|
| Session VWAP | price above VWAP (graded by distance in ATR) | 2.0 |
| EMA 9 / 21 | price > EMA 9 > EMA 21 | 1.5 |
| 1h trend | 1h close above a rising 50 EMA | 1.5 |
| Supertrend (2, 10) | uptrend | 1.0 |
| RSI (9) | above 50 | 1.0 |
| Volume flow | volume is concentrated in up-closing candles | 1.0 |

## Signals and filters
- **LONG** when score ≥ +50, **SHORT** when score ≤ -50, but only if:
  - inside the session (default 08:00–21:00 UTC = London + New York),
  - the signal candle has at least average volume (relative volume ≥ 1.0),
  - ADX ≥ 18 (the market is trending, not chopping),
  - at least 5 bars since the last signal.
- After a signal, the score has to cool off to half the threshold before the same direction can fire again,
  so it doesn't jump straight back in after a stop.
- Every trade gets a **stop at 1.5 × ATR** and a **target at 2R** (3 × ATR), drawn on the chart.
- Exits: **TP** (target hit), **SL** (stop hit), or grey **x** (score flipped past zero or the session ended).
- Grey background = outside the session (no new trades). Grey step lines = previous day's high and low.

## Alerts
Create an alert → condition *BTC Day Trading Model* → `BTC-DT long`, `BTC-DT short` or `BTC-DT exit`, trigger *Once per bar close*.

## Backtest
> ⚠️ **Backtested 2020–2026 on Binance BTCUSDT 15m: -98% with default settings, and every one of 32 variants lost money after fees.** See [`backtest/RESULTS.md`](backtest/RESULTS.md). Don't trade it with real money as is.

Add `btc_daytrade_strategy.pine` on your timeframe. It assumes 0.05% commission per side and 2 ticks of slippage.
Check net profit after fees, max drawdown and number of trades before trading it with real money.
