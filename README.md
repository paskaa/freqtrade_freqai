# FreqAI Trading Strategy - V34.21

## Strategy Overview

Alvinchen_v34_21 is an advanced short-only trading strategy for cryptocurrency futures on Bybit with Multi-Timeframe (MTF) analysis and aggressive ROI exits.

### Key Features (V34.21)

1. **Pure Short-Only Strategy**
   - Long entries completely disabled
   - Focus on shorting during bearish conditions
   - Key insight: Long trades were losing -34.47% while shorts only lost -1.86%

2. **Multi-Timeframe Analysis (MTF)**
   - 1h indicators: EMA20, EMA50, ADX for trend confirmation
   - 4h indicators: EMA50, ADX for direction filtering
   - 15m timeframe for entry signals

3. **Strict Entry Conditions**
   - Major (1h) bearish: EMA20 < EMA50
   - Minor (15m) bearish: EMA20 < EMA50
   - ADX > 35 (strong trend confirmation)
   - DI_diff < -8 (clear bearish)
   - MACD < 0
   - RSI between 20-45 (clear weakness but not oversold)

4. **Aggressive ROI Exits**
   - 0: 3% (immediate profit taking)
   - 15min: 2%
   - 60min: 1.5%
   - 240min: 1%
   - 720min: 0.5%
   - 1440min: 0 (breakeven)

## Backtest Results (1-Year)

| Version | Total Profit | Drawdown | Trades | Win Rate | Period |
|---------|-------------|----------|--------|----------|--------|
| **V34.21** | **+41.60%** | **25.47%** | **614** | **TBD** | 20250325-20260325 |
| V34.20 | TBD | - | - | - | 20250901-20260201 |
| V34.16 | +220 USDT | - | 2638 | 78.8% | 20250901-20260201 |
| V34.14 | -612 USDT | - | 1438 | 79.0% | 20250901-20260201 |
| V34.4 | 5394.93 USDT | - | 793 | 81.8% | 20260222-20260322 |

## Configuration Files

- `config_freqai_v34_21_prod.json` - Production config (API: 28081)
- Strategy: `Alvinchen_v34_21.py`

## Usage

### Backtesting
```bash
freqtrade backtesting \
    --config user_data/config_freqai_v34_21_prod.json \
    --strategy Alvinchen_v34_21 \
    --timerange 20250325-20260325
```

### Live Trading
```bash
freqtrade trade \
    --config user_data/config_freqai_v34_21_prod.json \
    --strategy Alvinchen_v34_21
```

## Key Changes from V34.20

1. **Disabled Long Entries**: `dataframe.loc[long_entry, 'enter_long'] = 1` commented out
2. **Strict Short Conditions**: Added ADX>35, DI_diff<-8, RSI<45 requirements
3. **Aggressive ROI**: Reduced from 15%/12%/8%/5%/3% to 3%/2%/1.5%/1%/0.5%/0%
4. **Removed Trailing Stop**: Disabled to avoid premature exits

## Changelog

### V34.21 (2026-03-25) - Current Production
- Pure short-only strategy (long entries disabled)
- 1-year backtest: +41.60% profit, 25.47% drawdown
- Aggressive ROI exits: 3% immediate -> 0% breakeven at 24h
- Strict entry: ADX>35, DI_diff<-8, RSI 20-45
- MTF confirmation: 1h bearish + 15m bearish

### V34.20 (2026-03-24)
- MTF analysis using `@informative` decorator
- 1h EMA20/EMA50/ADX/RSI for trend confirmation
- 4h EMA50/ADX for direction filtering

## Author

FreqTrade Bot

## License

MIT
