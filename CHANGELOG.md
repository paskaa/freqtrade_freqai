# Changelog

## [v4022] - 2026-04-02

### Added
- oversold_long条件收紧：新增RSI_2<20和MFI<25确认
- 价格位置阈值收紧：30→20
- RSI超卖阈值收紧：35→25

### Changed
- 熊市抄底做多条件更严格，避免过早抄底

### Performance
- 胜率提升: 64.7% → 69.3% (+4.6%)
- 总利润提升: 16656 USDT → 21557 USDT (+29.4%)
- 做多利润改善: -2716 USDT → +3805 USDT (+6521 USDT)
- Sharpe提升: 2.15 → 3.27 (+52%)
- 回测周期: 2025-04-01 ~ 2026-03-28 (1年)

## [v4018g] - 2026-04-01

### Changed
- confirm_trade_exit: 拒绝trailing_stop_exit当利润<3%且趋势延续
- level1_profit_exit reverse_signals阈值从3提高到4

### Performance
- 胜率: 63.7%
- 总利润: +20141 USDT (+67.14%)
- 回撤: 9.66%
