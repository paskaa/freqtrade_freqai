# FreqAI Trading Strategy - V35

## Strategy Overview

Alvinchen_v35 is an advanced multi-timeframe trading strategy for cryptocurrency futures on Bybit with optimized entry conditions for both long and short positions.

### Key Features (V35)

1. **Multi-Timeframe Analysis (MTF)**
   - 1h indicators: EMA20, EMA50, ADX for trend confirmation
   - 4h indicators: EMA50, ADX for direction filtering
   - 15m timeframe for entry signals

2. **Optimized Entry Conditions**
   - **Long**: ADX > 55, DI_diff > 20, RSI 60-65 (very strict)
   - **Short**: ADX > 35, DI_diff < -8, RSI 20-45 (strict)
   - MTF confirmation required for both directions

3. **Aggressive ROI Exits**
   - 0: 3% (immediate profit taking)
   - 15min: 2%
   - 60min: 1.5%
   - 240min: 1%
   - 720min: 0.5%
   - 1440min: 0 (breakeven)

## Backtest Results (1-Year)

| Version | Total Profit | Drawdown | Trades | Win Rate | Period |
|---------|-------------|----------|--------|----------|--------|
| **V35** | **+19.27%** | **17.34%** | **566** | **86.6%** | 20250325-20260325 |
| V34.21 (short-only) | +41.60% | 25.47% | 614 | - | 20250325-20260325 |

## Version History

- **V35**: Multi-directional (long+short) with optimized long conditions
- **V34.21**: Pure short-only strategy (best for bear markets)

## Configuration Files

- `config_freqai_v34_21_prod.json` - Production config (API: 28081)
- Strategy: `Alvinchen_v35.py`

## Usage

### Backtesting
```bash
freqtrade backtesting \
    --config user_data/config_freqai_v34_21_prod.json \
    --strategy Alvinchen_v35 \
    --timerange 20250325-20260325
```

### Live Trading
```bash
freqtrade trade \
    --config user_data/config_freqai_v34_21_prod.json \
    --strategy Alvinchen_v35
```

## Key Changes from V34.21

1. **Enabled Long Entries**: ADX>55, DI_diff>20, RSI 60-65
2. **Strict Short Conditions**: ADX>35, DI_diff<-8, RSI 20-45
3. **MTF Confirmation**: 1h + 15m required for all entries

## Changelog

See CHANGELOG.md for detailed version history.

## Author

FreqTrade Bot

## License

MIT
