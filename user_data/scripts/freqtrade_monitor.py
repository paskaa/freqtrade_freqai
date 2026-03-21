#!/usr/bin/env python3
"""
Freqtrade 日志监控脚本
定时检查日志中的错误，发现异常时自动调用Claude进行修复
"""

import os
import re
import json
import time
import subprocess
import hashlib
from datetime import datetime
from pathlib import Path

# 配置
LOG_FILE = "/root/ft_userdata/user_data/logs/freqtrade.log"
STATE_FILE = "/root/ft_userdata/user_data/scripts/freqtrade_monitor_state.json"
STRATEGY_FILE = "/root/ft_userdata/user_data/strategies/Alvinchen_15m131.py"
ERROR_COOLDOWN = 300  # 同类错误冷却时间(秒)
MAX_ERROR_LINES = 50  # 提取的最大错误行数

# 错误模式 (需要立即修复的严重错误)
CRITICAL_PATTERNS = [
    r"UnboundLocalError",
    r"NameError",
    r"TypeError",
    r"AttributeError",
    r"ImportError",
    r"ModuleNotFoundError",
    r"IndentationError",
    r"SyntaxError",
    r"ZeroDivisionError",
    r"IndexError",
    r"KeyError",
    r"RuntimeError",
    r"RecursionError",
    r"MemoryError",
    r"Exception.*strategy",
    r"Traceback \(most recent call last\)",
]

# 警告模式 (记录但不自动修复)
WARNING_PATTERNS = [
    r"WARNING.*insufficient",
    r"WARNING.*rate limit",
    r"WARNING.*timeout",
    r"WARNING.*connection",
]


def load_state():
    """加载状态文件"""
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, 'r') as f:
                return json.load(f)
        except:
            pass
    return {
        "last_position": 0,
        "processed_errors": {},
        "last_check": None
    }


def save_state(state):
    """保存状态文件"""
    state["last_check"] = datetime.now().isoformat()
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f, indent=2)


def get_error_hash(error_text):
    """计算错误的唯一哈希值"""
    # 提取错误类型和行号作为唯一标识
    key_parts = []
    for line in error_text.split('\n')[:5]:
        if 'Error' in line or 'File' in line:
            key_parts.append(line.strip())
    return hashlib.md5('|'.join(key_parts).encode()).hexdigest()[:12]


def extract_error_context(log_content, start_idx):
    """提取错误上下文"""
    lines = log_content.split('\n')
    error_lines = []
    in_traceback = False
    brace_count = 0

    for i in range(start_idx, min(start_idx + MAX_ERROR_LINES, len(lines))):
        line = lines[i]

        # 检测Traceback开始
        if 'Traceback' in line:
            in_traceback = True
            error_lines.append(line)
            continue

        if in_traceback:
            error_lines.append(line)
            # 检测错误结束
            if any(err in line for err in ['Error:', 'Exception:']):
                # 再收集几行额外信息
                for j in range(i+1, min(i+5, len(lines))):
                    if lines[j].strip() and not lines[j].startswith('202'):
                        error_lines.append(lines[j])
                break
        else:
            # 非Traceback错误
            if any(re.search(p, line) for p in CRITICAL_PATTERNS):
                error_lines.append(line)

    return '\n'.join(error_lines) if error_lines else None


def find_new_errors(log_content, last_position):
    """查找新错误"""
    errors = []

    # 从上次位置开始检查
    new_content = log_content[last_position:]
    if not new_content:
        return errors, len(log_content)

    lines = new_content.split('\n')
    current_idx = 0

    for i, line in enumerate(lines):
        # 检查是否匹配严重错误模式
        for pattern in CRITICAL_PATTERNS:
            if re.search(pattern, line):
                # 找到Traceback开始位置
                traceback_start = i
                for j in range(max(0, i-10), i):
                    if 'Traceback' in lines[j]:
                        traceback_start = j
                        break

                error_context = extract_error_context(new_content, traceback_start)
                if error_context:
                    errors.append({
                        'text': error_context,
                        'line': line,
                        'timestamp': datetime.now().isoformat()
                    })
                break

    return errors, last_position + len(log_content) - len(new_content) + len(new_content)


def call_claude_for_fix(error_info):
    """调用Claude修复错误"""

    prompt = f"""Freqtrade策略发生错误，请分析并修复：

## 错误日志
```
{error_info['text']}
```

## 策略文件
{STRATEGY_FILE}

## 任务
1. 分析错误原因
2. 定位策略文件中的问题代码
3. 修复bug
4. 重启freqtrade服务

请直接修复，不要询问确认。
"""

    # 构建claude命令
    claude_cmd = [
        "claude",
        "--print",
        prompt
    ]

    try:
        print(f"\n{'='*60}")
        print(f"[{datetime.now()}] 调用Claude修复错误...")
        print(f"{'='*60}\n")

        result = subprocess.run(
            claude_cmd,
            capture_output=True,
            text=True,
            timeout=300,  # 5分钟超时
            cwd="/root/ft_userdata/user_data/strategies"
        )

        print("Claude输出:")
        print(result.stdout)

        if result.stderr:
            print("错误信息:")
            print(result.stderr)

        return result.returncode == 0

    except subprocess.TimeoutExpired:
        print("Claude调用超时")
        return False
    except Exception as e:
        print(f"调用Claude失败: {e}")
        return False


def restart_freqtrade():
    """重启freqtrade"""
    print(f"\n[{datetime.now()}] 重启freqtrade...")

    # 停止现有进程
    subprocess.run(["pkill", "-f", "freqtrade trade"], capture_output=True)
    time.sleep(2)

    # 启动新进程
    cmd = [
        "/root/ft_userdata/.venv/bin/freqtrade",
        "trade",
        "--logfile", "/root/ft_userdata/user_data/logs/freqtrade.log",
        "--config", "/root/ft_userdata/user_data/config_trade_15m.json",
        "--strategy", "Alvinchen_15m131"
    ]

    subprocess.Popen(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True
    )

    time.sleep(3)

    # 验证启动
    result = subprocess.run(
        ["pgrep", "-f", "freqtrade trade"],
        capture_output=True,
        text=True
    )

    if result.stdout.strip():
        print(f"Freqtrade重启成功, PID: {result.stdout.strip()}")
        return True
    else:
        print("Freqtrade重启失败")
        return False


def send_notification(title, message):
    """发送通知 (可扩展为Telegram/微信等)"""
    # 这里可以添加Telegram/企业微信等通知
    print(f"\n🔔 [{title}] {message}\n")

    # 示例: 发送到文件记录
    notify_file = "/root/ft_userdata/user_data/logs/freqtrade_alerts.log"
    with open(notify_file, 'a') as f:
        f.write(f"[{datetime.now()}] {title}: {message}\n")


def main():
    """主监控循环"""
    print(f"[{datetime.now()}] Freqtrade日志监控启动")
    print(f"监控文件: {LOG_FILE}")
    print(f"策略文件: {STRATEGY_FILE}")
    print(f"检查间隔: 60秒\n")

    state = load_state()

    # 首次运行，获取当前日志位置
    if state["last_position"] == 0:
        try:
            with open(LOG_FILE, 'r') as f:
                f.seek(0, 2)  # 跳到文件末尾
                state["last_position"] = f.tell()
                save_state(state)
                print(f"初始化日志位置: {state['last_position']} bytes")
        except Exception as e:
            print(f"无法读取日志文件: {e}")
            return

    while True:
        try:
            # 读取日志
            with open(LOG_FILE, 'r') as f:
                f.seek(state["last_position"])
                new_content = f.read()

            if new_content:
                # 查找错误
                errors, new_position = find_new_errors(
                    open(LOG_FILE).read(),
                    state["last_position"]
                )

                # 处理每个错误
                for error in errors:
                    error_hash = get_error_hash(error['text'])

                    # 检查是否已处理过
                    if error_hash in state["processed_errors"]:
                        last_time = state["processed_errors"][error_hash]
                        if time.time() - last_time < ERROR_COOLDOWN:
                            print(f"跳过重复错误: {error_hash}")
                            continue

                    print(f"\n🚨 发现错误!")
                    print(f"错误哈希: {error_hash}")
                    print(f"错误内容:\n{error['text'][:500]}...")

                    # 发送通知
                    send_notification("Freqtrade错误", f"发现策略错误: {error['line'][:100]}")

                    # 调用Claude修复
                    if call_claude_for_fix(error):
                        # 重启freqtrade
                        restart_freqtrade()

                        # 标记错误已处理
                        state["processed_errors"][error_hash] = time.time()

                        # 清理旧记录
                        cutoff = time.time() - 86400  # 保留24小时
                        state["processed_errors"] = {
                            k: v for k, v in state["processed_errors"].items()
                            if v > cutoff
                        }
                    else:
                        send_notification("修复失败", "Claude未能修复错误，请手动处理")

                # 更新位置
                state["last_position"] = new_position
                save_state(state)

            # 等待下次检查
            time.sleep(60)

        except KeyboardInterrupt:
            print("\n监控停止")
            break
        except Exception as e:
            print(f"监控异常: {e}")
            time.sleep(60)


if __name__ == "__main__":
    main()