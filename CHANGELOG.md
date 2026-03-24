# Changelog

All notable changes to this project will be documented in this file.

## [v34.21] - 2026-03-25

### Added
- New strategy `Alvinchen_v34_21.py` - Pure short-only trading strategy
- Aggressive ROI exit settings: 3% -> 2% -> 1.5% -> 1% -> 0.5% -> 0%
- Strict short entry conditions: ADX>35, DI_diff<-8, RSI 20-45
- MTF confirmation: 1h bearish + 15m bearish required

### Changed
- Long entries completely disabled
- Trailing stop disabled
- ROI exits made more aggressive (3% immediate vs 15% original)
- 1-year backtest period: 20250325-20260325

### Performance (1-Year Backtest)
- Total Profit: **+41.60%**
- Drawdown: **25.47%**
- Trades: 614
- Key insight: Long trades lost -34.47%, shorts lost only -1.86%

### Production
- Config: `config_freqai_v34_21_prod.json`
- API Port: 28081
- Status: **Running**

## [v34.20] - 2026-03-24

### Added
- New strategy `Alvinchen_v34_20.py` with proper Multi-Timeframe (MTF) analysis
- `@informative` decorator for 1h and 4h timeframe indicators
- 1h indicators: EMA20, EMA50, ADX, RSI for trend confirmation
- 4h indicators: EMA50, ADX for direction filtering

### Changed
- MTF logic: Long requires 15m signal + 1h EMA20>EMA50 + 4h ADX>25 or price above 4h EMA50
- MTF logic: Short requires 15m signal + 1h EMA20<EMA50 + 4h ADX>25 or price below 4h EMA50
- Improved `populate_entry_trend` to use MTF columns with fallbacks

## [v34.19] - 2026-03-24

### Fixed
- Multi-asset balance check bug: Dynamic threshold based on `max_open_trades // 2`
- Short side now has same balance check logic as long side
- Fixed issue where single order incorrectly rejected due to `balance_check_threshold=0.75`

### Changed
- `balance_check_threshold` increased from 0.5 to 0.75 for more flexibility
- `sentiment_allow_contrarian_shorts: True` - allows shorting during extreme fear with high ADX

## [v34.16] - 2026-03-23

### Performance (Backtest 20250901-20260201)
- Total Profit: +220 USDT
- Total Trades: 2638
- Win Rate: 78.8%

## [v34.14] - 2026-03-22

### Performance (Backtest 20250901-20260201)
- Total Profit: -612 USDT
- Total Trades: 1438
- Win Rate: 79.0%

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
