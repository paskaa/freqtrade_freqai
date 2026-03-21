#!/bin/bash
# FreqAI策略回测脚本 v2
# 目标: 30天20%盈利
# 测试新增指标: TTM Squeeze, Wave Trend, Ichimoku, Supertrend

set -e

CONFIG_DIR="/root/ft_userdata/user_data"
STRATEGY="Alvinchen_15m131_FreqAI"
MODEL="LightGBMRegressor"

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}FreqAI策略回测${NC}"
echo -e "${GREEN}目标: 30天20%盈利${NC}"
echo -e "${GREEN}========================================${NC}"

cd /root/ft_userdata

# 回测时间范围 (最近30天)
START_DATE="20260219"
END_DATE="20260321"

echo -e "${YELLOW}回测参数:${NC}"
echo "  - 策略: $STRATEGY"
echo "  - 模型: $MODEL"
echo "  - 时间: $START_DATE 到 $END_DATE"
echo ""

# 检查数据
echo -e "${YELLOW}检查数据...${NC}"
python3 -c "
import pandas as pd
import os

pairs = ['BTC_USDT_USDT', 'ETH_USDT_USDT', 'SOL_USDT_USDT']
data_dir = '/root/ft_userdata/user_data/data/bybit/futures'

for pair in pairs:
    file = f'{data_dir}/{pair}-15m-futures.feather'
    if os.path.exists(file):
        df = pd.read_feather(file)
        print(f'{pair}: {len(df)}条, 最新: {df[\"date\"].max()}')
    else:
        print(f'{pair}: 数据文件不存在')
"

echo ""
echo -e "${YELLOW}开始回测 (这可能需要10-20分钟)...${NC}"
echo ""

# 运行回测
freqtrade backtesting \
    --config $CONFIG_DIR/config_backtest.json \
    --strategy $STRATEGY \
    --freqaimodel $MODEL \
    --timerange "$START_DATE-$END_DATE" \
    --dry-run-wallet 10000 \
    --max-open-trades 20 \
    --stake-amount unlimited \
    --export trades \
    2>&1 | tee /tmp/backtest_output.log

# 检查结果
if [ $? -eq 0 ]; then
    echo ""
    echo -e "${GREEN}========================================${NC}"
    echo -e "${GREEN}回测完成！${NC}"
    echo -e "${GREEN}========================================${NC}"

    # 提取关键指标
    echo -e "${YELLOW}关键指标:${NC}"
    grep -E "TOTAL|Win|Loss|Drawdown|Profit|Sharpe|CAGR" /tmp/backtest_output.log | tail -20

    echo ""
    echo -e "${YELLOW}详细结果保存在:${NC}"
    echo "  - 日志: /tmp/backtest_output.log"
    echo "  - 结果: $CONFIG_DIR/backtest_results/"
else
    echo -e "${RED}回测失败，请检查日志${NC}"
    tail -50 /tmp/backtest_output.log
fi