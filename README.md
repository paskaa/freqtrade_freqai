# FreqAI Trading Strategy - V34.4

## Strategy Overview

Alvinchen_v34_4 is an advanced FreqAI-based trading strategy for cryptocurrency futures on Bybit.

### Key Features (V34.4)

1. **ADX/DI Primary Entry + FreqAI Auxiliary**
   - ADX/DI technical indicators as primary entry conditions
   - FreqAI prediction as auxiliary judgment via `enter_tag`
   - No mandatory FreqAI filtering - preserves the original 15% profit logic

2. **Intelligent Position Sizing**
   - `custom_stake_amount` adjusts position size based on FreqAI confidence
   - FreqAI confirmed trades: 1.5x position size
   - Technical-only trades: 1.0x position size

3. **FreqAI Integration**
   - LightGBM Regressor model
   - Multi-timeframe: 15m + 1h
   - Single regression target: `&-s_close_mean` (rolling mean price change)
   - Prediction threshold: 0.002 (0.2%)

4. **Risk Management**
   - Stoploss: 50%
   - Max open trades: 30
   - Trailing stop loss enabled
   - Multiple ROI targets

## Backtest Results (V34.4)

| Metric | Result |
|--------|--------|
| **Total Profit** | **17.98%** (5394.93 USDT) |
| **Total Trades** | 793 |
| **Win Rate** | **81.8%** (649 wins / 144 losses) |
| **Profit Factor** | **2.25** |
| **Avg Duration** | 23h 8m |
| **Trading Pairs** | 60 |

## Configuration Files

- `config_freqai_v34_4_prod.json` - Production config (API: 28081)
- `config_freqai_v34_4.json` - Test/Dry-run config

## Usage

### Backtesting
```bash
freqtrade backtesting \
    --config user_data/config_freqai_v34_4.json \
    --strategy Alvinchen_v34_4 \
    --freqaimodel LightGBMRegressor \
    --timerange 20260222-20260322
```

### Live Trading
```bash
freqtrade trade \
    --config user_data/config_freqai_v34_4_prod.json \
    --strategy Alvinchen_v34_4 \
    --freqaimodel LightGBMRegressor
```

## Changelog

### V34.4 (2026-03-22) - Current Production
- ADX/DI + FreqAI auxiliary strategy
- 60 trading pairs, max 30 open trades
- 17.98% profit, 81.8% win rate
- API port: 28081

### V34.1 (2026-03-22)
- Fixed FreqAI training not starting issue
- Added `freqai.start()` call
- Single regression target

### V34.0 (2026-03-21)
- Initial FreqAI integration
- Bug: FreqAI training not started

### V31 (2026-03-21)
- Relaxed stoploss: 50% long, 25% short
- Added position adjustment

### V20
- Initial FreqAI version
- LightGBM model integration

## Author

FreqTrade Bot

## License

MIT