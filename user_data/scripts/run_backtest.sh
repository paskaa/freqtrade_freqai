#!/bin/bash
# FreqAI策略回测脚本
# 目标: 30天20%盈利
# 使用方法: ./run_backtest.sh [quick|full]

set -e

MODE=${1:-quick}
CONFIG_DIR="/root/ft_userdata/user_data"
STRATEGY="Alvinchen_15m131_FreqAI"
MODEL="LightGBMRegressor"

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}FreqAI策略回测${NC}"
echo -e "${GREEN}目标: 30天20%盈利${NC}"
echo -e "${GREEN}========================================${NC}"

cd /root/ft_userdata

if [ "$MODE" = "quick" ]; then
    echo -e "${YELLOW}快速回测模式 (最近30天)${NC}"
    START_DATE="2025-10-20"
    END_DATE="2025-11-20"
else
    echo -e "${YELLOW}完整回测模式 (最近90天)${NC}"
    START_DATE="2025-08-20"
    END_DATE="2025-11-20"
fi

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
        print(f'{pair}: {len(df)}条, {df[\"date\"].min().date()} 到 {df[\"date\"].max().date()}')
    else:
        print(f'{pair}: 数据文件不存在')
"

echo ""
echo -e "${YELLOW}开始回测...${NC}"
echo ""

# 运行回测
freqtrade backtesting \
    --config $CONFIG_DIR/config_freqai.json \
    --strategy $STRATEGY \
    --freqaimodel $MODEL \
    --timerange "$START_DATE-$END_DATE" \
    --timeframe-detail 15m \
    --enable-protections \
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
    grep -E "TOTAL|Win|Loss|Drawdown|Profit" /tmp/backtest_output.log | tail -10

    echo ""
    echo -e "${YELLOW}详细结果保存在:${NC}"
    echo "  - 日志: /tmp/backtest_output.log"
    echo "  - 结果: $CONFIG_DIR/backtest_results/"
else
    echo -e "${RED}回测失败，请检查日志${NC}"
    tail -50 /tmp/backtest_output.log
fi