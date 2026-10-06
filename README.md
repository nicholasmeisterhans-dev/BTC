# BTC Direction Model (TradingView / Pine Script v6)

| File | What it is |
|---|---|
| `btc_direction_model.pine` | The indicator: bias score, UP/DOWN signals, dashboard, alerts |
| `btc_direction_strategy.pine` | The same logic as a strategy, so you can backtest it in the Strategy Tester |

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
