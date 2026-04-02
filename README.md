# Freqtrade 加密货币交易策略

## 当前版本: v4022

### 性能指标 (1年回测 2025-04-01 ~ 2026-03-28)

| 指标 | 值 |
|------|-----|
| 交易数 | 456 |
| 胜率 | **69.3%** |
| 总利润 | **+21,557 USDT (+71.86%)** |
| 回撤 | 11.72% |
| Sharpe | **3.27** |
| Calmar | **32.45** |

### 核心策略特点

- **4层币种分级**: Tier1-Tier4不同阈值
- **ADX/DI趋势确认**: 确保入场质量
- **时间敏感止损**: 24h/48h/72h递进收紧
- **分层止盈**: 多档位锁定利润
- **熊市抄底优化**: 严格的oversold_long条件

### 快速开始

```bash
# 回测
python3 -m freqtrade backtesting \
  --config user_data/config_v40_prod.json \
  --strategy Alvinchen_v4022 \
  --timerange 20250401-20260328 \
  --timeframe 15m

# 生产运行
python3 -m freqtrade trade \
  --config user_data/config_v40_prod.json \
  --strategy Alvinchen_v4022
```

## 版本历史

| 版本 | 日期 | 胜率 | 利润 | 核心改进 |
|------|------|------|------|----------|
| v4022 | 2026-04-02 | **69.3%** | **+71.86%** | oversold_long收紧 |
| v4018g | 2026-04-01 | 63.7% | +67.14% | 出场确认优化 |
| v4017 | 2026-03-31 | 86.3% | +53.5% | 时间敏感止损 |

详见 [CHANGELOG.md](CHANGELOG.md)
