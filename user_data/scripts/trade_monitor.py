#!/usr/bin/env python3
"""
FreqAI 交易监控脚本
每小时检查交易情况，如果没有下单则适当调整参数

功能:
1. 检查过去1小时的交易数量
2. 如果没有交易，分析原因
3. 自动调整入场条件参数
4. 记录监控日志
"""

import json
import requests
import time
from datetime import datetime, timedelta
from pathlib import Path
import subprocess

# 配置
CONFIG_PATH = "/root/ft_userdata/user_data/config_freqai.json"
LOG_PATH = "/tmp/trade_monitor.log"
API_URL = "http://localhost:28081"
API_USER = "alvinchen1010"
API_PASS = "Fhzl1981302"

# 参数调整范围
PARAM_RANGES = {
    "buy_pred_threshold": {"min": 0.25, "max": 0.45, "step": 0.02, "current": 0.37},
    "adx_threshold": {"min": 18, "max": 25, "step": 1, "current": 21},
}

def log(msg):
    """写日志"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_msg = f"[{timestamp}] {msg}"
    print(log_msg)
    with open(LOG_PATH, "a") as f:
        f.write(log_msg + "\n")

def get_api_data(endpoint):
    """调用FreqUI API"""
    try:
        url = f"{API_URL}/api/v1/{endpoint}"
        response = requests.get(url, auth=(API_USER, API_PASS), timeout=10)
        if response.status_code == 200:
            return response.json()
        else:
            log(f"API错误: {response.status_code}")
            return None
    except Exception as e:
        log(f"API调用失败: {e}")
        return None

def get_trade_count(hours=1):
    """获取过去N小时的交易数量"""
    trades = get_api_data("trades")
    if not trades:
        return 0

    now = datetime.now()
    cutoff = now - timedelta(hours=hours)

    count = 0
    for trade in trades:
        open_date = datetime.fromisoformat(trade.get("open_date", "").replace("Z", "+00:00"))
        if open_date.replace(tzinfo=None) > cutoff:
            count += 1

    return count

def get_status():
    """获取当前状态"""
    status = get_api_data("status")
    profit = get_api_data("profit")

    return {
        "open_trades": len(status) if status else 0,
        "total_trades": profit.get("trade_count", 0) if profit else 0,
        "win_rate": profit.get("winrate", 0) if profit else 0,
        "profit_pct": profit.get("profit_all_percent", 0) if profit else 0
    }

def analyze_no_trade_reason():
    """分析不下单的原因"""
    reasons = []

    # 检查日志中的关键信息
    try:
        result = subprocess.run(
            ["tail", "-100", "/tmp/freqtrade_freqai.log"],
            capture_output=True, text=True, timeout=10
        )
        log_content = result.stdout.lower()

        if "no pair in whitelist" in log_content:
            reasons.append("交易对白名单为空")
        if "freqai" in log_content and "training" in log_content:
            reasons.append("FreqAI正在训练模型")
        if "rate limit" in log_content:
            reasons.append("API限流")
        if "insufficient" in log_content:
            reasons.append("余额不足")
        if "no signal" in log_content:
            reasons.append("没有入场信号")
    except Exception as e:
        log(f"分析日志失败: {e}")

    return reasons

def adjust_parameters():
    """调整策略参数"""
    # 读取当前策略参数
    strategy_path = "/root/freqtrade/user_data/strategies/Alvinchen_15m131_FreqAI.py"

    try:
        with open(strategy_path, "r") as f:
            content = f.read()

        adjustments = []

        # 调整 buy_pred_threshold (降低门槛，更容易入场)
        import re
        match = re.search(r'buy_pred_threshold = DecimalParameter\([^)]+default=([0-9.]+)', content)
        if match:
            current = float(match.group(1))
            new_val = max(current - 0.02, 0.25)  # 降低门槛
            if new_val != current:
                adjustments.append(f"buy_pred_threshold: {current:.3f} -> {new_val:.3f}")

        # 调整 ADX threshold (降低，更容易入场)
        match = re.search(r'adx_threshold = DecimalParameter\([^)]+default=([0-9.]+)', content)
        if match:
            current = float(match.group(1))
            new_val = max(current - 1, 18)
            if new_val != current:
                adjustments.append(f"adx_threshold: {current:.0f} -> {new_val:.0f}")

        if adjustments:
            log(f"建议调整参数: {', '.join(adjustments)}")
            log("注意: 参数调整需要重启bot才能生效")

        return adjustments
    except Exception as e:
        log(f"调整参数失败: {e}")
        return []

def main():
    log("=" * 50)
    log("开始监控交易状态...")

    # 获取当前状态
    status = get_status()
    log(f"当前状态: 持仓={status['open_trades']}, 总交易={status['total_trades']}, 胜率={status['win_rate']*100:.1f}%, 利润={status['profit_pct']:.2f}%")

    # 检查过去1小时的交易
    trade_count = get_trade_count(1)
    log(f"过去1小时交易数: {trade_count}")

    if trade_count == 0:
        log("⚠️ 过去1小时没有新交易，分析原因...")
        reasons = analyze_no_trade_reason()
        if reasons:
            for r in reasons:
                log(f"  - {r}")
        else:
            log("  未找到明确原因，可能是入场条件过于严格")

        # 分析并建议参数调整
        adjustments = adjust_parameters()
    else:
        log(f"✅ 有{trade_count}笔新交易，策略运行正常")

    log("监控完成")

if __name__ == "__main__":
    main()