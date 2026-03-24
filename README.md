# FreqAI Trading Strategy - V34.20

## Strategy Overview

Alvinchen_v34_20 is an advanced trading strategy for cryptocurrency futures on Bybit with Multi-Timeframe (MTF) analysis.

### Key Features (V34.20)

1. **Multi-Timeframe Analysis (MTF)**
   - Uses `@informative` decorator for clean MTF implementation
   - 1h indicators: EMA20, EMA50, ADX, RSI for trend confirmation
   - 4h indicators: EMA50, ADX for direction filtering
   - Proper backtesting support for MTF

2. **MTF Entry Logic**
   - Long: 15m signal + 1h EMA20>EMA50 + 4h ADX>25 or price above 4h EMA50
   - Short: 15m signal + 1h EMA20<EMA50 + 4h ADX>25 or price below 4h EMA50

3. **Sentiment Filter (v34.19)**
   - Allows contrarian shorts during extreme fear with high ADX
   - Dynamic balance check threshold: `max_open_trades // 2` per direction

4. **Risk Management**
   - Stoploss: 43.9% (long), 32.9% (short)
   - Max open trades: 30
   - Position adjustment enabled (DCA)

## Backtest Results

| Version | Total Profit | Trades | Win Rate | Period |
|---------|-------------|--------|----------|--------|
| **V34.20** | TBD (running) | - | - | 20250901-20260201 |
| **V34.16** | +220 USDT | 2638 | 78.8% | 20250901-20260201 |
| **V34.14** | -612 USDT | 1438 | 79.0% | 20250901-20260201 |
| V34.4 | 5394.93 USDT | 793 | 81.8% | 20260222-20260322 |

## Configuration Files

- `config_freqai_v34_19_prod.json` - Production config (API: 28081)
- Strategy: `Alvinchen_v34_20.py`

## Usage

### Backtesting
```bash
freqtrade backtesting \
    --config user_data/config_freqai_v34_19_prod.json \
    --strategy Alvinchen_v34_20 \
    --timerange 20250901-20260201
```

### Live Trading
```bash
freqtrade trade \
    --config user_data/config_freqai_v34_19_prod.json \
    --strategy Alvinchen_v34_20
```

## Changelog

### V34.20 (2026-03-24) - Current
- MTF analysis using `@informative` decorator
- 1h EMA20/EMA50/ADX/RSI for trend confirmation
- 4h EMA50/ADX for direction filtering

### V34.19 (2026-03-24)
- Fixed multi-asset balance check bug
- Dynamic threshold: max_open_trades // 2 per direction
- Contrarian shorts allowed during extreme fear with high ADX

### V34.16 (2026-03-23)
- Best backtest performance: +220 USDT, 78.8% win rate

### V34.14 (2026-03-22)
- -612 USDT, 79.0% win rate

### V34.4 (2026-03-22)
- Initial production version
- 17.98% profit, 81.8% win rate

## Author

FreqTrade Bot

## License

MIT