# Changelog

All notable changes to this project will be documented in this file.

## [v35] - 2026-03-25

### Added
- New strategy `Alvinchen_v35.py` with multi-directional trading (long + short)
- Optimized long entry conditions: ADX>55, DI_diff>20, RSI 60-65
- Short entry conditions: ADX>35, DI_diff<-8, RSI 20-45

### Changed
- Version naming: V35, V36, V37... (sequential major versions)
- Long entries now enabled with strict conditions
- Multi-Timeframe confirmation required for both directions

### Performance (1-Year Backtest)
- Total Profit: **+19.27%**
- Drawdown: **17.34%**
- Trades: 566
- Win Rate: 86.6%
- Long trades: 23 (profit +5.59%)
- Short trades: 543 (profit +13.68%)

### Production
- Config: `config_freqai_v34_21_prod.json`
- API Port: 28081
- Status: **Running**

## [v34.21] - 2026-03-25

### Added
- Pure short-only trading strategy
- Aggressive ROI exit settings: 3% -> 2% -> 1.5% -> 1% -> 0.5% -> 0%
- Strict short entry conditions: ADX>35, DI_diff<-8, RSI 20-45

### Changed
- Long entries completely disabled
- Trailing stop disabled

### Performance (1-Year Backtest)
- Total Profit: +41.60%
- Drawdown: 25.47%
- Trades: 614

### Known Issue
- Long entries disabled (may miss opportunities in bull markets)

## [v34.20] - 2026-03-24

### Added
- `@informative` decorator for 1h and 4h timeframe indicators
- 1h indicators: EMA20, EMA50, ADX, RSI for trend confirmation
- 4h indicators: EMA50, ADX for direction filtering

## [v34.19] - 2026-03-24

### Fixed
- Multi-asset balance check bug: Dynamic threshold based on `max_open_trades // 2`

## [v34.16] - 2026-03-23

### Performance (Backtest 20250901-20260201)
- Total Profit: +220 USDT
- Total Trades: 2638
- Win Rate: 78.8%

## [v34.4] - 2026-03-22

### Added
- ADX/DI + FreqAI auxiliary approach
- Production config with 60 trading pairs

### Performance
- Total Profit: 17.98% (5394.93 USDT)
- Win Rate: 81.8%
- Total Trades: 793

## [v20.0] - Initial Release

### Added
- FreqAI integration with LightGBM model
- Sentiment/On-chain/News filters
- Basic technical indicators (RSI, MACD, EMA)
