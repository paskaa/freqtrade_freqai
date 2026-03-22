# Changelog

All notable changes to this project will be documented in this file.

## [v34.4] - 2026-03-22

### Added
- New strategy `Alvinchen_v34_4.py` with ADX/DI + FreqAI auxiliary approach
- FreqAI prediction as `enter_tag` marker instead of mandatory filter
- `custom_stake_amount` for position sizing based on FreqAI confidence
- Production config `config_freqai_v34_4_prod.json` with 60 trading pairs

### Changed
- Max open trades increased to 30
- API port changed to 28081
- Single regression target `&-s_close_mean`
- Prediction threshold set to 0.002 (0.2%)

### Performance
- Total Profit: 17.98% (5394.93 USDT)
- Win Rate: 81.8% (649 wins / 144 losses)
- Profit Factor: 2.25
- Total Trades: 793

## [v34.1] - 2026-03-22

### Fixed
- Added `freqai.start()` call to fix FreqAI training not starting
- Single regression target to avoid multi-target errors

### Changed
- Prediction threshold adjusted from 0.55 to 0.003
- ROI relaxed to 20%/12%/8%/5%/3%/0%

## [v34.0] - 2026-03-21

### Added
- Initial FreqAI integration with LightGBM
- ADX/DI technical indicators as entry conditions
- Multi-timeframe support (15m, 1h, 4h)

### Known Issues
- FreqAI training not starting (fixed in v34.1)

## [v31.0] - 2026-03-19

### Changed
- Stoploss relaxed: 50% for long, 25% for short
- Added position adjustment strategy
- ROI optimization: 12%/8%/5%/3%/2%/1%

## [v20.0] - Initial Release

### Added
- FreqAI integration with LightGBM model
- Sentiment/On-chain/News filters
- Basic technical indicators (RSI, MACD, EMA)