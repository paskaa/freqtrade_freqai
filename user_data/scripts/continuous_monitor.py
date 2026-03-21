#!/usr/bin/env python3
"""
FreqAI 持续监控与优化系统
- 实时监控交易表现
- 自动执行定期回测验证
- 检测策略衰减并触发重新优化
"""

import os
import sys
import json
import time
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
import requests
from typing import Dict, List, Optional

# 配置
BASE_DIR = Path("/root/ft_userdata")
USER_DATA = BASE_DIR / "user_data"
LOGS_DIR = USER_DATA / "logs"
BACKTEST_DIR = USER_DATA / "backtest_results"
CONFIG_FILE = USER_DATA / "config_freqai.json"
STRATEGY = "Alvinchen_15m131_FreqAI"
API_URL = "http://localhost:28081"
API_USER = "alvinchen1010"
API_PASS = "Fhzl1981302"

# 监控状态
monitor_state = {
    "start_time": datetime.now().isoformat(),
    "total_trades": 0,
    "total_profit": 0,
    "win_count": 0,
    "loss_count": 0,
    "daily_reports": [],
    "alerts": [],
    "last_optimization": None,
    "optimization_count": 0
}


def log(message: str, level: str = "INFO"):
    """写入日志"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_line = f"[{timestamp}] [{level}] {message}"
    print(log_line)

    log_file = LOGS_DIR / "monitor.log"
    with open(log_file, "a") as f:
        f.write(log_line + "\n")


def api_request(endpoint: str, method: str = "GET", data: dict = None) -> Optional[dict]:
    """调用Freqtrade API"""
    try:
        url = f"{API_URL}/api/v1/{endpoint}"
        auth = (API_USER, API_PASS)

        if method == "GET":
            response = requests.get(url, auth=auth, timeout=10)
        else:
            response = requests.post(url, auth=auth, json=data, timeout=10)

        if response.status_code == 200:
            return response.json()
    except Exception as e:
        log(f"API请求失败: {endpoint} - {e}", "ERROR")
    return None


def get_trade_status() -> Dict:
    """获取交易状态"""
    status = {
        "running": False,
        "open_trades": 0,
        "positions": [],
        "total_profit": 0,
        "daily_profit": 0
    }

    # 检查进程
    result = subprocess.run(
        ["pgrep", "-f", "freqtrade trade"],
        capture_output=True, text=True
    )
    status["running"] = bool(result.stdout.strip())

    # 获取API数据
    data = api_request("status")
    if data:
        status["open_trades"] = len(data)
        for trade in data:
            profit = trade.get("profit_ratio", 0)
            status["total_profit"] += profit
            status["positions"].append({
                "pair": trade.get("pair"),
                "profit": profit * 100,
                "duration": trade.get("open_date")
            })

    # 获取每日盈亏
    profit_data = api_request("profit")
    if profit_data:
        status["daily_profit"] = profit_data.get("profit_all_coin", 0)

    return status


def get_performance_metrics() -> Dict:
    """获取性能指标"""
    metrics = {
        "total_trades": 0,
        "wins": 0,
        "losses": 0,
        "win_rate": 0,
        "avg_profit": 0,
        "total_profit": 0,
        "max_drawdown": 0
    }

    data = api_request("trade_stats")
    if data:
        # 解析交易统计
        stats = data.get("stats", {})
        metrics["total_trades"] = stats.get("total_trades", 0)
        metrics["wins"] = stats.get("wins", 0)
        metrics["losses"] = stats.get("losses", 0)
        metrics["win_rate"] = stats.get("winning_trades_pct", 0)

    return metrics


def run_backtest(timerange: str = None) -> Dict:
    """执行回测验证"""
    log(f"开始回测验证 - {timerange or 'default'}")

    cmd = [
        "/root/ft_userdata/.venv/bin/freqtrade",
        "backtesting",
        "--config", str(CONFIG_FILE),
        "--strategy", STRATEGY,
        "--freqaimodel", "LightGBMRegressor"
    ]

    if timerange:
        cmd.extend(["--timerange", timerange])

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=1800,  # 30分钟超时
            cwd=str(BASE_DIR)
        )

        output = result.stdout + result.stderr

        # 解析结果
        metrics = {
            "success": result.returncode == 0,
            "output": output[-5000:],  # 保留最后5000字符
            "profit": 0,
            "trades": 0,
            "win_rate": 0
        }

        # 提取关键指标
        import re
        profit_match = re.search(r"Total profit:\s*([\d.]+)%", output)
        if profit_match:
            metrics["profit"] = float(profit_match.group(1))

        trades_match = re.search(r"Total trades:\s*(\d+)", output)
        if trades_match:
            metrics["trades"] = int(trades_match.group(1))

        win_match = re.search(r"Win rate:\s*([\d.]+)%", output)
        if win_match:
            metrics["win_rate"] = float(win_match.group(1))

        log(f"回测完成 - 收益: {metrics['profit']}%, 交易: {metrics['trades']}, 胜率: {metrics['win_rate']}%")
        return metrics

    except subprocess.TimeoutExpired:
        log("回测超时", "ERROR")
        return {"success": False, "error": "timeout"}
    except Exception as e:
        log(f"回测失败: {e}", "ERROR")
        return {"success": False, "error": str(e)}


def check_strategy_health() -> Dict:
    """检查策略健康状态"""
    health = {
        "status": "healthy",
        "issues": [],
        "recommendations": []
    }

    # 获取最近交易表现
    status = get_trade_status()
    metrics = get_performance_metrics()

    # 检查连续亏损
    recent_loss = 0
    if metrics["losses"] > metrics["wins"] * 1.5:
        health["issues"].append("连续亏损过多")
        health["recommendations"].append("考虑调整入场条件或暂停交易")

    # 检查持仓时间过长
    for pos in status["positions"]:
        if pos.get("duration"):
            try:
                open_time = datetime.fromisoformat(pos["duration"].replace("Z", "+00:00"))
                hours = (datetime.now(open_time.tzinfo) - open_time).total_seconds() / 3600
                if hours > 48:
                    health["issues"].append(f"持仓时间过长: {pos['pair']} ({hours:.1f}小时)")
            except:
                pass

    # 检查浮亏过大
    if status["total_profit"] < -0.1:  # -10%
        health["issues"].append(f"总浮亏过大: {status['total_profit']*100:.1f}%")
        health["status"] = "warning"

    if health["issues"]:
        health["status"] = "warning" if len(health["issues"]) < 3 else "critical"

    return health


def generate_report() -> str:
    """生成监控报告"""
    status = get_trade_status()
    health = check_strategy_health()

    report = f"""
========================================
FreqAI 监控报告
时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
========================================

【运行状态】
- 进程状态: {'✅ 运行中' if status['running'] else '❌ 已停止'}
- 当前持仓: {status['open_trades']} 个
- 总浮盈: {status['total_profit']*100:.2f}%
- 每日盈亏: {status['daily_profit']:.4f} USDT

【策略健康】
- 状态: {health['status'].upper()}
- 问题: {len(health['issues'])} 个
"""

    if health["issues"]:
        report += "\n【警告事项】\n"
        for issue in health["issues"]:
            report += f"- {issue}\n"

    if status["positions"]:
        report += "\n【当前持仓】\n"
        for pos in status["positions"]:
            report += f"- {pos['pair']}: {pos['profit']:.2f}%\n"

    return report


def optimize_strategy(reason: str = "scheduled") -> bool:
    """触发策略优化"""
    log(f"触发策略优化 - 原因: {reason}")

    # 记录优化事件
    monitor_state["optimization_count"] += 1
    monitor_state["last_optimization"] = datetime.now().isoformat()

    # 运行hyperopt
    cmd = [
        "/root/ft_userdata/.venv/bin/freqtrade",
        "hyperopt",
        "--config", str(CONFIG_FILE),
        "--strategy", STRATEGY,
        "--freqaimodel", "LightGBMRegressor",
        "--hyperopt-loss", "SharpeHyperOptLoss",
        "--spaces", "buy", "roi", "stoploss",
        "--epochs", "50",
        "--timerange", "20250201-20260319"
    ]

    try:
        log("开始Hyperopt优化...")
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=7200,  # 2小时超时
            cwd=str(BASE_DIR)
        )

        if result.returncode == 0:
            log("Hyperopt优化完成")
            # 保存优化历史
            history_file = USER_DATA / "scripts" / "optimization_history.json"
            history = []
            if history_file.exists():
                with open(history_file, "r") as f:
                    history = json.load(f)

            history.append({
                "timestamp": datetime.now().isoformat(),
                "reason": reason,
                "output": result.stdout[-2000:]
            })

            with open(history_file, "w") as f:
                json.dump(history[-50:], f, indent=2)

            return True
        else:
            log(f"Hyperopt失败: {result.stderr[:500]}", "ERROR")
            return False

    except Exception as e:
        log(f"优化过程出错: {e}", "ERROR")
        return False


def save_state():
    """保存监控状态"""
    state_file = USER_DATA / "scripts" / "monitor_state.json"
    with open(state_file, "w") as f:
        json.dump(monitor_state, f, indent=2)


def main():
    """主监控循环"""
    log("=" * 50)
    log("FreqAI 持续监控系统启动")
    log(f"策略: {STRATEGY}")
    log("=" * 50)

    # 初始健康检查
    health = check_strategy_health()
    log(f"策略健康状态: {health['status']}")

    # 生成初始报告
    report = generate_report()
    print(report)

    # 主循环 - 每5分钟检查一次
    check_interval = 300  # 5分钟
    backtest_interval = 86400  # 24小时
    last_backtest = time.time()

    while True:
        try:
            # 状态检查
            status = get_trade_status()

            # 生成报告（每小时）
            if datetime.now().minute == 0:
                report = generate_report()
                log(report)
                save_state()

            # 健康检查
            health = check_strategy_health()
            if health["status"] == "critical":
                log(f"严重警告: {health['issues']}", "CRITICAL")
                # 可以添加自动通知逻辑

            # 定期回测验证（每24小时）
            if time.time() - last_backtest > backtest_interval:
                log("执行定期回测验证...")
                backtest_result = run_backtest("20250301-20260319")

                if backtest_result.get("success"):
                    # 检查回测表现是否下降
                    if backtest_result.get("profit", 0) < 20:  # 低于20%
                        log("回测表现下降，触发优化", "WARNING")
                        optimize_strategy("performance_decline")

                last_backtest = time.time()

            time.sleep(check_interval)

        except KeyboardInterrupt:
            log("监控停止")
            break
        except Exception as e:
            log(f"监控异常: {e}", "ERROR")
            time.sleep(60)


if __name__ == "__main__":
    main()