#!/usr/bin/env python3
"""
FreqAI 优化监控系统 - Web Dashboard
提供实时监控、回测结果可视化、优化进度追踪
"""

import os
import json
import time
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from flask import Flask, render_template, jsonify, request
from flask_cors import CORS
import threading

# 配置路径 - 支持源码运行和Docker运行
BASE_DIR = Path("/root/ft_userdata")
USER_DATA = BASE_DIR / "user_data"
STRATEGIES_DIR = USER_DATA / "strategies"
LOGS_DIR = USER_DATA / "logs"
BACKTEST_DIR = USER_DATA / "backtest_results"
CONFIG_DIR = USER_DATA
TEMPLATES_DIR = USER_DATA / "templates"

# 源码运行路径
SOURCE_BASE_DIR = Path("/root/freqtrade")
SOURCE_USER_DATA = SOURCE_BASE_DIR / "user_data"
SOURCE_LOGS_DIR = SOURCE_USER_DATA / "logs"
SOURCE_STRATEGIES_DIR = SOURCE_USER_DATA / "strategies"

# 实际使用的路径(优先源码路径)
ACTIVE_LOGS_DIR = SOURCE_LOGS_DIR if SOURCE_LOGS_DIR.exists() else LOGS_DIR
ACTIVE_STRATEGIES_DIR = SOURCE_STRATEGIES_DIR if SOURCE_STRATEGIES_DIR.exists() else STRATEGIES_DIR

# 源码运行的输出日志
SOURCE_OUTPUT_LOG = Path("/tmp/freqtrade_output.log")

# 配置Flask应用
app = Flask(__name__, template_folder=str(TEMPLATES_DIR))
CORS(app)

# 数据存储
optimization_data = {
    "status": "idle",
    "current_step": "",
    "progress": 0,
    "history": [],
    "backtest_results": [],
    "metrics": {}
}


def get_freqai_status():
    """获取FreqAI进程状态"""
    try:
        result = subprocess.run(
            ["pgrep", "-f", "freqtrade.*trade"],
            capture_output=True, text=True
        )
        if result.stdout.strip():
            pids = result.stdout.strip().split('\n')
            # 获取主进程PID
            main_pid = pids[0] if pids else None

            # 检查是否是FreqAI策略
            is_freqai = False
            try:
                cmd_result = subprocess.run(
                    ["ps", "-p", main_pid, "-o", "args="],
                    capture_output=True, text=True
                )
                if "FreqAI" in cmd_result.stdout or "LightGBM" in cmd_result.stdout:
                    is_freqai = True
            except:
                pass

            return {
                "running": True,
                "pid": main_pid,
                "mode": "freqai" if is_freqai else "standard"
            }
    except:
        pass

    return {"running": False, "pid": None, "mode": "none"}


def parse_log_file(log_file, lines=500):
    """解析日志文件"""
    if not log_file.exists():
        return []

    try:
        with open(log_file, 'r') as f:
            content = f.readlines()[-lines:]

        logs = []
        for line in content:
            try:
                timestamp = line.split(']')[0].replace('[', '') if ']' in line else ''
                level = 'INFO'
                for lvl in ['ERROR', 'WARNING', 'CRITICAL', 'DEBUG']:
                    if lvl in line[:100]:
                        level = lvl
                        break

                logs.append({
                    "timestamp": timestamp,
                    "level": level,
                    "message": line.strip()
                })
            except:
                continue

        return logs
    except:
        return []


def get_backtest_results():
    """获取回测结果 - 支持zip格式"""
    import zipfile
    results = []

    if BACKTEST_DIR.exists():
        # 首先检查zip文件
        zip_files = sorted(BACKTEST_DIR.glob("*.zip"), key=lambda x: x.stat().st_mtime, reverse=True)[:10]
        for zf in zip_files:
            try:
                with zipfile.ZipFile(zf, 'r') as z:
                    # 找到json结果文件
                    json_files = [f for f in z.namelist() if f.endswith('.json') and 'config' not in f]
                    if json_files:
                        with z.open(json_files[0]) as f:
                            data = json.load(f)

                        strategy = list(data.get('strategy', {}).keys())[0] if data.get('strategy') else 'Unknown'
                        metrics = data.get('strategy', {}).get(strategy, {})

                        results.append({
                            "file": zf.name,
                            "strategy": strategy,
                            "date": datetime.fromtimestamp(zf.stat().st_mtime).strftime('%Y-%m-%d %H:%M'),
                            "total_trades": metrics.get('total_trades', 0),
                            "profit_mean": metrics.get('profit_mean', 0),
                            "profit_total": metrics.get('profit_total', 0),
                            "win_rate": metrics.get('wins', 0) / max(metrics.get('total_trades', 1), 1) * 100,
                            "max_drawdown": metrics.get('max_drawdown_absolute', 0),
                            "sharpe": metrics.get('sharpe', 0),
                            "sortino": metrics.get('sortio', 0) or metrics.get('sortino', 0),
                            "cagr": metrics.get('cagr', 0)
                        })
            except Exception as e:
                print(f"Error reading {zf}: {e}")
                continue

        # 如果没有zip文件，尝试读取json文件
        if not results:
            for f in sorted(BACKTEST_DIR.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True)[:10]:
                try:
                    with open(f, 'r') as fp:
                        data = json.load(fp)

                    strategy = list(data.get('strategy', {}).keys())[0] if data.get('strategy') else 'Unknown'
                    metrics = data.get('strategy', {}).get(strategy, {})

                    results.append({
                        "file": f.name,
                        "strategy": strategy,
                        "date": datetime.fromtimestamp(f.stat().st_mtime).strftime('%Y-%m-%d %H:%M'),
                        "total_trades": metrics.get('total_trades', 0),
                        "profit_mean": metrics.get('profit_mean', 0),
                        "profit_total": metrics.get('profit_total', 0),
                        "win_rate": metrics.get('wins', 0) / max(metrics.get('total_trades', 1), 1) * 100,
                        "max_drawdown": metrics.get('max_drawdown_absolute', 0),
                        "sharpe": metrics.get('sharpe', 0)
                    })
                except:
                    continue

    return results


def get_trading_metrics():
    """从数据库或日志获取交易指标"""
    metrics = {
        "open_trades": 0,
        "total_profit": 0,
        "win_rate": 0,
        "daily_profit": 0,
        "positions": []
    }

    # 尝试从API获取
    try:
        import requests
        response = requests.get(
            "http://localhost:28081/api/v1/status",
            auth=("alvinchen1010", "Fhzl1981302"),
            timeout=5
        )
        if response.status_code == 200:
            data = response.json()
            metrics["open_trades"] = len(data)

            total_profit = 0
            wins = 0
            for trade in data:
                total_profit += trade.get('profit_ratio', 0)
                if trade.get('profit_ratio', 0) > 0:
                    wins += 1
                metrics["positions"].append({
                    "pair": trade.get('pair', ''),
                    "profit": trade.get('profit_ratio', 0) * 100,
                    "duration": trade.get('open_date', '')
                })

            metrics["total_profit"] = total_profit * 100
            metrics["win_rate"] = wins / max(len(data), 1) * 100
    except:
        pass

    return metrics


def get_optimization_history():
    """获取优化历史"""
    history_file = USER_DATA / "scripts" / "optimization_history.json"
    if history_file.exists():
        try:
            with open(history_file, 'r') as f:
                return json.load(f)
        except:
            pass
    return []


def save_optimization_step(step_data):
    """保存优化步骤"""
    history_file = USER_DATA / "scripts" / "optimization_history.json"
    history = get_optimization_history()
    history.append(step_data)

    # 只保留最近50条
    if len(history) > 50:
        history = history[-50:]

    with open(history_file, 'w') as f:
        json.dump(history, f, indent=2)


def run_backtest_async(strategy, config):
    """异步运行回测"""
    global optimization_data

    optimization_data["status"] = "running"
    optimization_data["current_step"] = f"Running backtest for {strategy}"
    optimization_data["progress"] = 0

    cmd = [
        "/root/ft_userdata/.venv/bin/freqtrade",
        "backtesting",
        "--config", str(config),
        "--strategy", strategy,
        "--timerange", "20250101-20260319"
    ]

    # 如果是FreqAI策略
    if "FreqAI" in strategy:
        cmd.extend(["--freqaimodel", "LightGBMRegressor"])

    try:
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            cwd=str(BASE_DIR)
        )

        output_lines = []
        while True:
            line = process.stdout.readline()
            if not line and process.poll() is not None:
                break
            if line:
                output_lines.append(line)
                optimization_data["current_step"] = line.strip()[:100]

                # 更新进度
                if "Loading data" in line:
                    optimization_data["progress"] = 10
                elif "Running backtesting" in line:
                    optimization_data["progress"] = 30
                elif "Calculating" in line:
                    optimization_data["progress"] = 70
                elif "Result" in line:
                    optimization_data["progress"] = 90

        process.wait()

        # 解析结果
        result_file = BACKTEST_DIR / f"backtest-result-{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        if result_file.exists():
            optimization_data["backtest_results"] = get_backtest_results()

        step_data = {
            "timestamp": datetime.now().isoformat(),
            "action": "backtest",
            "strategy": strategy,
            "status": "completed" if process.returncode == 0 else "failed",
            "output": ''.join(output_lines[-100:])
        }
        save_optimization_step(step_data)
        optimization_data["history"].append(step_data)

    except Exception as e:
        optimization_data["history"].append({
            "timestamp": datetime.now().isoformat(),
            "action": "backtest",
            "strategy": strategy,
            "status": "error",
            "error": str(e)
        })

    optimization_data["status"] = "idle"
    optimization_data["progress"] = 100


# ==================== API Routes ====================

@app.route('/')
def dashboard():
    """主仪表板"""
    return render_template('dashboard.html')


@app.route('/api/status')
def api_status():
    """获取系统状态"""
    return jsonify({
        "freqai": get_freqai_status(),
        "optimization": optimization_data,
        "timestamp": datetime.now().isoformat()
    })


@app.route('/api/metrics')
def api_metrics():
    """获取交易指标"""
    return jsonify(get_trading_metrics())


@app.route('/api/backtest/results')
def api_backtest_results():
    """获取回测结果"""
    return jsonify(get_backtest_results())


@app.route('/api/logs')
def api_logs():
    """获取日志"""
    # 优先使用源码运行输出日志
    if SOURCE_OUTPUT_LOG.exists():
        log_file = SOURCE_OUTPUT_LOG
    elif (ACTIVE_LOGS_DIR / "freqtrade.log").exists():
        log_file = ACTIVE_LOGS_DIR / "freqtrade.log"
    else:
        log_file = LOGS_DIR / "freqtrade.log"
    lines = request.args.get('lines', 200, type=int)
    return jsonify(parse_log_file(log_file, lines))


@app.route('/api/optimization/history')
def api_optimization_history():
    """获取优化历史"""
    return jsonify(get_optimization_history())


@app.route('/api/backtest/run', methods=['POST'])
def api_run_backtest():
    """运行回测"""
    data = request.json
    strategy = data.get('strategy', 'Alvinchen_15m131_FreqAI')
    config = data.get('config', 'config_freqai.json')

    config_path = CONFIG_DIR / config

    # 异步执行
    thread = threading.Thread(
        target=run_backtest_async,
        args=(strategy, str(config_path))
    )
    thread.daemon = True
    thread.start()

    return jsonify({"status": "started", "strategy": strategy})


@app.route('/api/service/control', methods=['POST'])
def api_service_control():
    """控制服务"""
    data = request.json
    action = data.get('action')

    # 源码运行的启动命令
    start_cmd = [
        "python3", "-m", "freqtrade", "trade",
        "--config", str(SOURCE_USER_DATA / "config_freqai.json"),
        "--strategy", "Alvinchen_15m131_FreqAI",
        "--freqaimodel", "LightGBMRegressor"
    ]

    if action == 'start_freqai':
        # 设置PYTHONPATH
        env = os.environ.copy()
        env["PYTHONPATH"] = f"{SOURCE_STRATEGIES_DIR}:{env.get('PYTHONPATH', '')}"
        subprocess.Popen(start_cmd, cwd=str(SOURCE_BASE_DIR), env=env, start_new_session=True)
        return jsonify({"status": "starting", "service": "freqai"})

    elif action == 'stop_freqai':
        subprocess.run(["pkill", "-f", "freqtrade.*trade"], capture_output=True)
        return jsonify({"status": "stopping", "service": "freqai"})

    elif action == 'restart_freqai':
        subprocess.run(["pkill", "-f", "freqtrade.*trade"], capture_output=True)
        time.sleep(2)
        env = os.environ.copy()
        env["PYTHONPATH"] = f"{SOURCE_STRATEGIES_DIR}:{env.get('PYTHONPATH', '')}"
        subprocess.Popen(start_cmd, cwd=str(SOURCE_BASE_DIR), env=env, start_new_session=True)
        return jsonify({"status": "restarting", "service": "freqai"})

    return jsonify({"status": "unknown action"})


@app.route('/api/strategies')
def api_strategies():
    """获取策略列表"""
    strategies = []
    strategies_dir = ACTIVE_STRATEGIES_DIR if ACTIVE_STRATEGIES_DIR.exists() else STRATEGIES_DIR
    for f in strategies_dir.glob("*.py"):
        if not f.name.startswith('_'):
            strategies.append({
                "name": f.stem,
                "file": f.name,
                "modified": datetime.fromtimestamp(f.stat().st_mtime).strftime('%Y-%m-%d %H:%M')
            })
    return jsonify(strategies)


@app.route('/api/config/freqai')
def api_config_freqai():
    """获取FreqAI配置"""
    config_file = CONFIG_DIR / "config_freqai.json"
    if config_file.exists():
        with open(config_file, 'r') as f:
            return jsonify(json.load(f))
    return jsonify({})


if __name__ == '__main__':
    # 创建模板目录
    templates_dir = BASE_DIR / "user_data" / "templates"
    templates_dir.mkdir(exist_ok=True)

    print(f"[{datetime.now()}] FreqAI Optimization Dashboard starting on port 5001")
    app.run(host='0.0.0.0', port=5001, debug=False, threaded=True)