# Backtest: BTC Day Trading Model

**Data:** Binance BTCUSDT perpetual, 15m bars, 2020-09-01 → 2026-09-09 (211,189 bars), from
[kbsingh1399/Backtesting_Data](https://github.com/kbsingh1399/Backtesting_Data) (`Binance_Data/BTCUSDT_15m_master_2020_2026.parquet`).
Year-end closes match known BTC history.

**Method:** `backtest_daytrade.py` re-implements `btc_daytrade_strategy.pine` in Python (Pine-style EMA/RMA,
Supertrend, ADX, daily VWAP, non-repainting 1h trend). It fills orders at the next bar's open like TradingView,
and fills stops and targets intrabar (stop first if both are hit). 100% of equity per trade, $10,000 start.

## Default settings (15m, threshold 50, 1.5×ATR stop, 2R target, longs + shorts)

| Fee per side | Net return (6 yrs) | Profit factor | Max drawdown |
|---|---|---|---|
| 0.05% (default) | **-98.2%** | 0.82 | -98.3% |
| 0.02% | -76.7% | 0.91 | -81.0% |
| 0% (no fees) | +25.9% | 1.02 | -53.5% |
| Buy and hold | **+571.8%** | | |

- 4,219 trades (~1.9 per day), 35% win rate.
- Lost money in **every** calendar year 2020–2026.
- Longs and shorts were equally bad (both 35% win rate).

## Variants (fees 0.05%), chosen on 2020–2023, checked on 2024–2026

Tried 32 combinations: chart 15m / 1h, threshold 50 / 65, stop 1.5 / 3 ×ATR, target 2R / 3R, with/without shorts.
**All 32 lost money in both periods.** Best in 2020–2023: 1h, threshold 65, long-only, 1.5 ATR stop, 3R target:
profit factor 0.98 (-3.6%) in 2020–2023, then 0.78 (-31.7%) in 2024–2026.

## Conclusion
The model has no edge large enough to cover trading costs. The signals are roughly break-even before
fees, and frequent intraday trading turns that into large losses. Don't trade it with real money as is.

Run it yourself: `python backtest_daytrade.py BTCUSDT_15m.parquet [--threshold 65] [--commission 0.02] [--no-shorts]`
