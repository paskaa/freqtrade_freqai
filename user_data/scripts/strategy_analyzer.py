#!/usr/bin/env python3
"""
FreqAI策略优化分析脚本
目标: 30天20%盈利

功能:
1. 分析当前策略参数
2. 计算理论收益目标
3. 提供优化建议
"""

import json
import os
from datetime import datetime, timedelta

CONFIG_FILE = "/root/ft_userdata/user_data/config_freqai.json"
STRATEGY_FILE = "/root/ft_userdata/user_data/strategies/Alvinchen_15m131_FreqAI.py"

def load_config():
    with open(CONFIG_FILE, 'r') as f:
        return json.load(f)

def analyze_strategy():
    """分析当前策略配置"""
    print("=" * 60)
    print("FreqAI策略分析报告")
    print("=" * 60)

    config = load_config()

    # 1. 基本配置
    print("\n【基本配置】")
    print(f"  交易所: {config['exchange']['name']}")
    print(f"  交易模式: {config.get('trading_mode', 'spot')}")
    print(f"  最大持仓: {config.get('max_open_trades', 10)}")
    print(f"  干跑模式: {config.get('dry_run', True)}")
    print(f"  止损: {config.get('stoploss', 'N/A')}")

    # 2. FreqAI配置
    print("\n【FreqAI配置】")
    freqai = config.get('freqai', {})
    print(f"  启用: {freqai.get('enabled', False)}")
    print(f"  训练周期: {freqai.get('train_period_days', 0)}天")
    print(f"  回测周期: {freqai.get('backtest_period_days', 0)}天")
    print(f"  实时重训练: {freqai.get('live_retrain_hours', 0)}小时")

    # 3. 模型参数
    print("\n【模型参数】")
    model_params = freqai.get('model_training_parameters', {})
    print(f"  n_estimators: {model_params.get('n_estimators', 'N/A')}")
    print(f"  max_depth: {model_params.get('max_depth', 'N/A')}")
    print(f"  learning_rate: {model_params.get('learning_rate', 'N/A')}")
    print(f"  num_leaves: {model_params.get('num_leaves', 'N/A')}")

    # 4. 交易对
    print("\n【交易对】")
    whitelist = config['exchange'].get('pair_whitelist', [])
    print(f"  白名单: {len(whitelist)}个")
    for pair in whitelist[:10]:
        print(f"    - {pair}")
    if len(whitelist) > 10:
        print(f"    ... 还有{len(whitelist)-10}个")

    # 5. 收益目标计算
    print("\n【收益目标分析】")
    print("  目标: 30天20%盈利")

    # 计算每日所需收益
    daily_target = (1.20 ** (1/30) - 1) * 100
    print(f"  每日目标收益: {daily_target:.3f}%")

    # 计算每笔交易所需收益 (假设每天2笔)
    trades_per_day = 2
    trade_target = daily_target / trades_per_day
    print(f"  假设每天{trades_per_day}笔交易, 每笔需要: {trade_target:.3f}%")

    # 资金管理
    print("\n【资金管理建议】")
    initial_capital = 4280  # 当前余额
    target_profit = initial_capital * 0.20
    print(f"  初始资金: ${initial_capital:.2f}")
    print(f"  目标利润: ${target_profit:.2f}")
    print(f"  目标期末资金: ${initial_capital + target_profit:.2f}")

    # 风险评估
    print("\n【风险评估】")
    stoploss = abs(config.get('stoploss', 0.05))
    print(f"  单笔最大亏损: {stoploss*100:.1f}%")
    print(f"  单笔最大亏损金额: ${initial_capital * stoploss:.2f}")
    print(f"  可承受连续亏损次数: {int(0.20 / stoploss)}次 (总资金20%风险)")

    return config

def generate_optimization_suggestions():
    """生成优化建议"""
    print("\n" + "=" * 60)
    print("优化建议")
    print("=" * 60)

    suggestions = [
        {
            "title": "入场条件优化",
            "current": "ADX > 30, DI_diff > 25, EMA完全排列",
            "issue": "条件过于严格，可能错过有效信号",
            "suggestion": "考虑降低ADX阈值到25，或允许部分EMA排列"
        },
        {
            "title": "止损优化",
            "current": "固定5.5%止损",
            "issue": "不考虑波动性，可能被噪音止损",
            "suggestion": "考虑ATR动态止损 (1.5-2倍ATR)"
        },
        {
            "title": "止盈优化",
            "current": "ROI: 8%/5%/3%/2%/1%",
            "issue": "可能过早止盈，限制盈利空间",
            "suggestion": "提高第一阶段ROI到10%，延长盈利持有时间"
        },
        {
            "title": "模型参数优化",
            "current": "n_estimators=500, max_depth=6",
            "issue": "可能欠拟合",
            "suggestion": "尝试增加n_estimators到800，或max_depth到8"
        },
        {
            "title": "杠杆策略",
            "current": "禁用杠杆",
            "issue": "错失高置信度交易机会",
            "suggestion": "对置信度>0.85的交易使用1.5-2x杠杆"
        }
    ]

    for i, s in enumerate(suggestions, 1):
        print(f"\n{i}. {s['title']}")
        print(f"   当前: {s['current']}")
        print(f"   问题: {s['issue']}")
        print(f"   建议: {s['suggestion']}")

def calculate_required_metrics():
    """计算达到目标所需的关键指标"""
    print("\n" + "=" * 60)
    print("目标达成所需指标")
    print("=" * 60)

    # 假设参数
    win_rate = 0.50  # 胜率
    avg_win = 0.03   # 平均盈利
    avg_loss = 0.055  # 平均亏损 (止损)

    print("\n【场景分析】")
    print(f"  假设胜率: {win_rate*100:.0f}%")
    print(f"  假设平均盈利: {avg_win*100:.1f}%")
    print(f"  假设平均亏损: {avg_loss*100:.1f}%")

    # 期望值
    expectancy = (win_rate * avg_win) - ((1 - win_rate) * avg_loss)
    print(f"\n  期望值: {expectancy*100:.2f}%/笔")

    # 达到20%所需的交易次数
    target = 0.20
    trades_needed = target / expectancy if expectancy > 0 else float('inf')
    print(f"  达到20%收益所需交易: {trades_needed:.0f}笔")

    # 每日交易需求
    days = 30
    trades_per_day = trades_needed / days
    print(f"  每日需交易: {trades_per_day:.1f}笔")

    # 不同胜率下的表现
    print("\n【不同胜率下的期望值】")
    print(f"  胜率 | 期望值/笔 | 30天所需交易")
    print("-" * 40)
    for wr in [0.40, 0.45, 0.50, 0.55, 0.60]:
        exp = (wr * avg_win) - ((1-wr) * avg_loss)
        needed = target / exp if exp > 0 else float('inf')
        print(f"  {wr*100:.0f}%  | {exp*100:+.2f}%    | {needed:.0f}笔")

    # 提高盈利/亏损比的影响
    print("\n【提高盈利/亏损比的影响】")
    print("  (假设胜率50%)")
    print(f"  盈利/亏损比 | 期望值/笔")
    print("-" * 30)
    for ratio in [0.5, 0.6, 0.7, 0.8, 1.0]:
        avg_win_test = avg_loss * ratio
        exp = 0.5 * avg_win_test - 0.5 * avg_loss
        print(f"  {ratio:.1f}:1       | {exp*100:+.2f}%")

if __name__ == "__main__":
    analyze_strategy()
    generate_optimization_suggestions()
    calculate_required_metrics()

    print("\n" + "=" * 60)
    print("下一步:")
    print("  1. 运行回测: ./run_backtest.sh quick")
    print("  2. 分析回测结果")
    print("  3. 根据结果调整参数")
    print("  4. 重新回测验证")
    print("=" * 60)