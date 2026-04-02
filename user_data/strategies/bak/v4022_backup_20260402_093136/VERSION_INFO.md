# v4022 版本备份

## 备份时间
$(date '+%Y-%m-%d %H:%M:%S')

## 回测结果 (2025-04-01 ~ 2026-03-28)

| 指标 | 值 |
|------|-----|
| 交易数 | 456 |
| 胜率 | **69.3%** |
| 总利润 | **21557 USDT (+71.86%)** |
| 回撤 | 11.72% |
| Sharpe | **3.27** |
| Calmar | **32.45** |
| 做多利润 | +3805 USDT |
| 做空利润 | +17752 USDT |

## 核心优化

基于v4018g_orig，只修改了oversold_long条件（熊市抄底做多）：

```python
# v4018g_orig:
oversold_long = (
    (dataframe['rsi'] < 35) &
    (dataframe['price_position'] < 30) &
    ...
)

# v4022: 更严格
oversold_long = (
    (dataframe['rsi'] < 25) &        # 35 → 25
    (dataframe['rsi_2'] < 20) &      # 新增
    (dataframe['price_position'] < 20) &  # 30 → 20
    (dataframe['mfi'] < 25) &        # 新增
    ...
)
```

## 相比v4018g_orig改进

| 指标 | v4018g_orig | v4022 | 变化 |
|------|-------------|-------|------|
| 利润 | 16656 USDT | 21557 USDT | **+29.4%** |
| 胜率 | 64.7% | 69.3% | **+4.6%** |
| 做多利润 | -2716 USDT | +3805 USDT | **+6521 USDT** |
| Sharpe | 2.15 | 3.27 | **+52%** |

## 文件列表

- `Alvinchen_v4022.py` - 策略文件
- `config_v40_prod.json` - 配置文件
- `VERSION_INFO.md` - 版本说明
