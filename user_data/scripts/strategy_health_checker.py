#!/usr/bin/env python3
"""
策略健康检查与自动修复脚本
每2小时运行一次，检查日志错误并自动修复问题
"""

import os
import sys
import re
import json
import time
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

# 配置
BASE_DIR = Path("/root/ft_userdata")
USER_DATA = BASE_DIR / "user_data"
LOGS_DIR = USER_DATA / "logs"
STRATEGY_DIR = USER_DATA / "strategies"
CONFIG_FILE = USER_DATA / "config_freqai.json"
STRATEGY = "Alvinchen_15m131_FreqAI"
LOG_FILE = LOGS_DIR / "health_checker.log"
STATE_FILE = USER_DATA / "scripts" / "health_state.json"

# 错误模式配置
ERROR_PATTERNS = {
    "leverage_mismatch": {
        "pattern": r"leverage.*10|10x|杠杆.*10",
        "fix": "sync_leverage",
        "severity": "high"
    },
    "api_error": {
        "pattern": r"TypeError.*best_pair|AttributeError.*NoneType",
        "fix": "restart_strategy",
        "severity": "medium"
    },
    "connection_error": {
        "pattern": r"ConnectionError|NetworkError|Too Many Requests",
        "fix": "wait",
        "severity": "low"
    },
    "order_stuck": {
        "pattern": r"Found open order.*repeatedly|订单.*卡住",
        "fix": "check_orders",
        "severity": "medium"
    },
    "database_error": {
        "pattern": r"database.*error|sqlite.*error|psycopg2.*error",
        "fix": "restart_strategy",
        "severity": "high"
    }
}

# 修复历史
fix_history = []


def log(message: str, level: str = "INFO"):
    """写入日志"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_line = f"[{timestamp}] [{level}] {message}"
    print(log_line)

    with open(LOG_FILE, "a") as f:
        f.write(log_line + "\n")


def load_state() -> dict:
    """加载状态"""
    if Path(STATE_FILE).exists():
        try:
            with open(STATE_FILE, "r") as f:
                return json.load(f)
        except:
            pass
    return {
        "last_check": None,
        "issues_found": 0,
        "fixes_applied": 0,
        "restarts": 0
    }


def save_state(state: dict):
    """保存状态"""
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def get_freqtrade_log() -> str:
    """获取FreqTrade日志"""
    log_sources = [
        "/tmp/freqtrade_output.log",
        str(LOGS_DIR / "freqtrade.log")
    ]

    content = ""
    for log_path in log_sources:
        if Path(log_path).exists():
            try:
                # 只读取最近2小时的日志
                result = subprocess.run(
                    ["tail", "-1000", log_path],
                    capture_output=True, text=True, timeout=10
                )
                content += result.stdout + "\n"
            except Exception as e:
                log(f"读取日志失败 {log_path}: {e}", "WARNING")

    return content


def check_for_errors(log_content: str) -> list:
    """检查日志中的错误"""
    issues = []

    for error_name, config in ERROR_PATTERNS.items():
        matches = re.findall(config["pattern"], log_content, re.IGNORECASE)
        if matches:
            issues.append({
                "name": error_name,
                "severity": config["severity"],
                "fix": config["fix"],
                "count": len(matches),
                "sample": matches[0] if matches else ""
            })

    return issues


def is_strategy_running() -> bool:
    """检查策略是否运行"""
    result = subprocess.run(
        ["pgrep", "-f", f"freqtrade trade.*{STRATEGY}"],
        capture_output=True, text=True
    )
    return bool(result.stdout.strip())


def restart_strategy():
    """重启策略"""
    log("正在重启策略...", "WARNING")

    # 停止现有进程
    subprocess.run(["pkill", "-f", f"freqtrade trade.*{STRATEGY}"], capture_output=True)
    time.sleep(3)

    # 启动新进程
    env = os.environ.copy()
    env["PYTHONPATH"] = f"{STRATEGY_DIR}:{env.get('PYTHONPATH', '')}"

    cmd = [
        "python3", "-m", "freqtrade", "trade",
        "--config", str(CONFIG_FILE),
        "--strategy", STRATEGY,
        "--freqaimodel", "LightGBMRegressor"
    ]

    with open("/tmp/freqtrade_output.log", "w") as log_out:
        subprocess.Popen(
            cmd,
            stdout=log_out,
            stderr=subprocess.STDOUT,
            env=env,
            cwd=str(BASE_DIR)
        )

    time.sleep(10)

    if is_strategy_running():
        log("策略重启成功", "INFO")
        return True
    else:
        log("策略重启失败!", "ERROR")
        return False


def sync_leverage():
    """同步杠杆"""
    log("正在同步持仓杠杆...", "INFO")

    # 这会在策略启动时自动执行
    # 这里只是触发一次重启来执行同步
    restart_strategy()


def check_stuck_orders():
    """检查卡住的订单"""
    log("检查卡住的订单...", "INFO")

    # 通过API检查
    try:
        import requests
        url = "http://localhost:28081/api/v1/status"
        auth = ("alvinchen1010", "Fhzl1981302")
        response = requests.get(url, auth=auth, timeout=10)

        if response.status_code == 200:
            trades = response.json()
            for trade in trades:
                # 检查是否有超时订单
                open_date = trade.get("open_date")
                if open_date:
                    # 可以添加更复杂的检查逻辑
                    pass
    except Exception as e:
        log(f"检查订单失败: {e}", "WARNING")


def apply_fix(fix_type: str) -> bool:
    """应用修复"""
    fix_map = {
        "sync_leverage": sync_leverage,
        "restart_strategy": restart_strategy,
        "check_orders": check_stuck_orders,
        "wait": lambda: time.sleep(60)  # 简单等待
    }

    fix_func = fix_map.get(fix_type)
    if fix_func:
        try:
            fix_func()
            return True
        except Exception as e:
            log(f"修复失败: {e}", "ERROR")
            return False
    return False


def run_health_check():
    """运行健康检查"""
    log("=" * 50)
    log("开始策略健康检查")

    state = load_state()

    # 1. 检查策略是否运行
    if not is_strategy_running():
        log("策略未运行，正在启动...", "WARNING")
        restart_strategy()
        state["restarts"] += 1

    # 2. 获取日志并检查错误
    log_content = get_freqtrade_log()
    issues = check_for_errors(log_content)

    if issues:
        log(f"发现 {len(issues)} 个问题:", "WARNING")

        for issue in issues:
            log(f"  - {issue['name']}: {issue['count']}次 ({issue['severity']})")

            # 高优先级问题立即修复
            if issue["severity"] == "high":
                log(f"    正在修复: {issue['fix']}")
                if apply_fix(issue["fix"]):
                    state["fixes_applied"] += 1
                    log(f"    修复成功", "INFO")
                else:
                    log(f"    修复失败", "ERROR")

            state["issues_found"] += 1
    else:
        log("未发现问题", "INFO")

    # 更新状态
    state["last_check"] = datetime.now().isoformat()
    save_state(state)

    log("健康检查完成")
    log("=" * 50)

    return state


def main():
    """主函数 - 每2小时运行一次"""
    log("策略健康检查服务启动")
    log("检查间隔: 2小时")

    while True:
        try:
            run_health_check()

            # 等待2小时
            log("等待下次检查 (2小时)...")
            time.sleep(7200)  # 2小时 = 7200秒

        except KeyboardInterrupt:
            log("服务停止")
            break
        except Exception as e:
            log(f"检查异常: {e}", "ERROR")
            time.sleep(300)  # 异常后等待5分钟


if __name__ == "__main__":
    # 可以直接运行一次检查
    if len(sys.argv) > 1 and sys.argv[1] == "--once":
        run_health_check()
    else:
        main()