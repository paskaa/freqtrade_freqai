#!/usr/bin/env python3
"""
FreqAI 持续优化服务
定期运行回测、分析结果、自动调优参数
"""

import os
import json
import time
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

# 配置
BASE_DIR = Path("/root/ft_userdata")
USER_DATA = BASE_DIR / "user_data"
STRATEGIES_DIR = USER_DATA / "strategies"
LOGS_DIR = USER_DATA / "logs"
BACKTEST_DIR = USER_DATA / "backtest_results"
STATE_FILE = USER_DATA / "scripts" / "optimization_state.json"
HISTORY_FILE = USER_DATA / "scripts" / "optimization_history.json"

# FreqAI配置
FREQAI_CONFIG = USER_DATA / "config_freqai.json"
FREQAI_STRATEGY = "Alvinchen_15m131_FreqAI"

# 优化参数范围
PARAM_RANGES = {
    "rsi_entry_threshold": {"min": 25, "max": 40, "step": 5},
    "rsi_exit_threshold": {"min": 60, "max": 80, "step": 5},
    "atr_stoploss_multiplier": {"min": 1.5, "max": 3.0, "step": 0.5},
    "volume_threshold": {"min": 1.5, "max": 3.0, "step": 0.5}
}


def load_state():
    """加载状态"""
    if STATE_FILE.exists():
        try:
            with open(STATE_FILE, 'r') as f:
                return json.load(f)
        except:
            pass
    return {
        "last_optimization": None,
        "optimization_count": 0,
        "best_params": {},
        "performance_history": []
    }


def save_state(state):
    """保存状态"""
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f, indent=2)


def log(message, level="INFO"):
    """记录日志"""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    log_message = f"[{timestamp}] [{level}] {message}"
    print(log_message)

    # 写入日志文件
    log_file = LOGS_DIR / "optimization.log"
    with open(log_file, 'a') as f:
        f.write(log_message + '\n')


def run_backtest(strategy, timerange=None, extra_params=None):
    """运行回测"""
    cmd = [
        "/root/ft_userdata/.venv/bin/freqtrade",
        "backtesting",
        "--config", str(FREQAI_CONFIG),
        "--strategy", strategy,
        "--freqaimodel", "LightGBMRegressor"
    ]

    if timerange:
        cmd.extend(["--timerange", timerange])
    else:
        # 默认最近60天
        end_date = datetime.now()
        start_date = end_date - timedelta(days=60)
        cmd.extend(["--timerange", f"{start_date.strftime('%Y%m%d')}-{end_date.strftime('%Y%m%d')}"])

    log(f"Running backtest: {' '.join(cmd)}")

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=1800,  # 30分钟超时
            cwd=str(BASE_DIR)
        )

        # 解析结果
        return parse_backtest_result(result.stdout)

    except subprocess.TimeoutExpired:
        log("Backtest timeout", "ERROR")
        return None
    except Exception as e:
        log(f"Backtest error: {e}", "ERROR")
        return None


def parse_backtest_result(output):
    """解析回测结果"""
    result = {
        "total_trades": 0,
        "profit_total": 0,
        "win_rate": 0,
        "max_drawdown": 0,
        "sharpe": 0,
        "raw_output": output
    }

    try:
        # 尝试从最新结果文件读取
        result_files = sorted(BACKTEST_DIR.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True)
        if result_files:
            with open(result_files[0], 'r') as f:
                data = json.load(f)

            strategy_data = list(data.get('strategy', {}).values())
            if strategy_data:
                metrics = strategy_data[0]
                result = {
                    "total_trades": metrics.get('total_trades', 0),
                    "profit_total": metrics.get('profit_total', 0),
                    "win_rate": metrics.get('wins', 0) / max(metrics.get('total_trades', 1), 1) * 100,
                    "max_drawdown": metrics.get('max_drawdown_absolute', 0),
                    "sharpe": metrics.get('sharpe', 0),
                    "avg_profit": metrics.get('profit_mean', 0) * 100
                }
    except Exception as e:
        log(f"Parse error: {e}", "WARNING")

    return result


def analyze_performance(state):
    """分析性能并生成优化建议"""
    history = state.get("performance_history", [])
    if len(history) < 2:
        return None

    recent = history[-5:]  # 最近5次
    avg_profit = sum(h.get("profit_total", 0) for h in recent) / len(recent)
    avg_win_rate = sum(h.get("win_rate", 0) for h in recent) / len(recent)

    suggestions = []

    # 分析胜率
    if avg_win_rate < 50:
        suggestions.append({
            "area": "entry_conditions",
            "issue": "low_win_rate",
            "suggestion": "Tighten entry conditions - increase RSI threshold",
            "priority": "high"
        })

    # 分析盈亏比
    if avg_profit < 0:
        suggestions.append({
            "area": "stoploss",
            "issue": "negative_profit",
            "suggestion": "Adjust ATR stoploss multiplier or trailing stop",
            "priority": "critical"
        })

    # 分析最大回撤
    avg_dd = sum(h.get("max_drawdown", 0) for h in recent) / len(recent)
    if avg_dd < -20:
        suggestions.append({
            "area": "risk_management",
            "issue": "high_drawdown",
            "suggestion": "Reduce position size or tighten stop loss",
            "priority": "high"
        })

    return suggestions


def generate_optimization_report(state, backtest_result):
    """生成优化报告"""
    report = {
        "timestamp": datetime.now().isoformat(),
        "optimization_number": state.get("optimization_count", 0) + 1,
        "backtest_result": backtest_result,
        "suggestions": analyze_performance(state),
        "current_params": state.get("best_params", {})
    }

    return report


def save_history(entry):
    """保存历史记录"""
    history = []
    if HISTORY_FILE.exists():
        try:
            with open(HISTORY_FILE, 'r') as f:
                history = json.load(f)
        except:
            pass

    history.append(entry)

    # 只保留最近50条
    if len(history) > 50:
        history = history[-50:]

    with open(HISTORY_FILE, 'w') as f:
        json.dump(history, f, indent=2)


def run_hyperopt(epochs=50):
    """运行Hyperopt优化"""
    log(f"Starting hyperopt optimization with {epochs} epochs")

    cmd = [
        "/root/ft_userdata/.venv/bin/freqtrade",
        "hyperopt",
        "--config", str(FREQAI_CONFIG),
        "--strategy", FREQAI_STRATEGY,
        "--hyperopt-loss", "WinDrawLossRatioHyperOptLoss",
        "--epochs", str(epochs),
        "--spaces", "buy sell"
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=7200,  # 2小时超时
            cwd=str(BASE_DIR)
        )

        log("Hyperopt completed")
        return result.stdout

    except subprocess.TimeoutExpired:
        log("Hyperopt timeout", "ERROR")
        return None
    except Exception as e:
        log(f"Hyperopt error: {e}", "ERROR")
        return None


def check_and_optimize():
    """主优化检查函数"""
    state = load_state()
    now = datetime.now()

    # 检查是否需要运行优化
    last_opt = state.get("last_optimization")
    if last_opt:
        last_opt_time = datetime.fromisoformat(last_opt)
        # 每24小时运行一次
        if (now - last_opt_time) < timedelta(hours=24):
            log("Skipping optimization - ran recently")
            return

    log("=" * 60)
    log("Starting optimization cycle")
    log("=" * 60)

    # 运行回测
    log("Running backtest...")
    result = run_backtest(FREQAI_STRATEGY)

    if result:
        log(f"Backtest result: {result}")

        # 更新状态
        state["last_optimization"] = now.isoformat()
        state["optimization_count"] = state.get("optimization_count", 0) + 1
        state["performance_history"].append(result)

        # 保留最近20次
        if len(state["performance_history"]) > 20:
            state["performance_history"] = state["performance_history"][-20:]

        save_state(state)

        # 生成报告
        report = generate_optimization_report(state, result)
        save_history(report)

        log("Optimization cycle completed")

        # 分析建议
        suggestions = report.get("suggestions")
        if suggestions:
            log("Optimization suggestions:")
            for s in suggestions:
                log(f"  [{s['priority']}] {s['area']}: {s['suggestion']}")

    else:
        log("Backtest failed - skipping optimization", "ERROR")


def main():
    """主函数"""
    log("FreqAI Optimization Service started")
    log(f"Strategy: {FREQAI_STRATEGY}")
    log(f"Config: {FREQAI_CONFIG}")

    while True:
        try:
            check_and_optimize()

            # 等待下一次检查 (每小时检查一次)
            log("Sleeping for 1 hour...")
            time.sleep(3600)

        except KeyboardInterrupt:
            log("Service stopped")
            break
        except Exception as e:
            log(f"Service error: {e}", "ERROR")
            time.sleep(300)  # 5分钟后重试


if __name__ == "__main__":
    main()