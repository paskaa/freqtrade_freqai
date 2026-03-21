# FreqAI Trading Strategy - V31

## Strategy Overview

Alvinchen_15m131_FreqAI is an advanced FreqAI-based trading strategy for cryptocurrency futures.

### Key Features (V31)

1. **放宽止损策略**
   - 多单止损: 50% (给足波动空间)
   - 空单止损: 25% (控制风险)

2. **智能补仓**
   - 亏损5%触发补仓
   - 最多补仓3次
   - 补仓比例: 初始仓位的50%
   - 信号验证后才补仓

3. **FreqAI集成**
   - LightGBM回归模型
   - 多时间框架: 15m + 1h
   - 高胜率指标: ROC, RSI, MFI

4. **风险管理**
   - 移动止损锁定利润
   - 多层ROI止盈
   - 情绪/链上/新闻过滤

## Configuration Files

- `config_freqai.json` - 生产环境配置
- `config_backtest.json` - 回测配置

## Usage

### Backtesting
```bash
freqtrade backtesting \
    --config user_data/config_backtest.json \
    --strategy Alvinchen_15m131_FreqAI \
    --freqaimodel LightGBMRegressor \
    --timerange 20260219-20260321 \
    --dry-run-wallet 10000 \
    --max-open-trades 20
```

### Live Trading
```bash
freqtrade trade \
    --config user_data/config_freqai.json \
    --strategy Alvinchen_15m131_FreqAI \
    --freqaimodel LightGBMRegressor
```

## Changelog

### V31 (2026-03-21)
- 放宽止损: 多单50%, 空单25%
- 添加补仓策略
- 优化ROI配置

### V20
- 初始FreqAI版本
- LightGBM模型集成
- 情绪/链上/新闻过滤

## Author

FreqTrade Bot

## License

MIT