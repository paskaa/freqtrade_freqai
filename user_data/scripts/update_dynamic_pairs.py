#!/usr/bin/env python3
"""
动态更新FreqAI交易对脚本
每2小时运行一次，根据以下条件更新交易对列表：
1. 支持合约交易（LinearPerpetual永续合约）
2. 24小时交易量排名
3. 支持做多做空
"""

import json
import requests
import time
from datetime import datetime, timedelta
from pathlib import Path

# 配置
CONFIG_PATH = "/root/ft_userdata/user_data/config.json"
LOG_PATH = "/tmp/dynamic_pairs.log"

# 筛选参数
TOP_N_PAIRS = 100           # 选择前N个交易对
MIN_VOLUME_USDT = 2000000  # 最小24h交易量 (USDT) - 降低门槛
MIN_DAYS_LISTED = 10       # 最小上市天数

# 主流币优先列表 (优先选择)
PRIORITY_COINS = [
    "BTC", "ETH", "SOL", "XRP", "DOGE", "ADA", "AVAX", "LINK", "DOT",
    "ARB", "OP", "MATIC", "ATOM", "LTC", "NEAR", "FIL", "INJ", "SUI",
    "BNB", "APT", "WIF", "AAVE", "WLD", "TAO", "NEIRO", "VIRTUAL", "MOVE"
]

# 黑名单
BLACKLIST = ["TRUMP/USDT:USDT", "PEPE/USDT:USDT", "BONK/USDT:USDT"]

# Meme币列表 (限制数量)
MEME_COINS = ["FARTCOIN", "LYN", "BAN", "PIPPIN", "SAHARA"]

def log(msg):
    """写日志"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_msg = f"[{timestamp}] {msg}"
    print(log_msg)
    with open(LOG_PATH, "a") as f:
        f.write(log_msg + "\n")

def get_bybit_instruments():
    """获取Bybit所有合约交易对信息"""
    try:
        proxies = {
            "http": "http://127.0.0.1:18080",
            "https": "http://127.0.0.1:18080"
        }
        # 使用instruments-info获取合约信息
        url = "https://api.bybit.com/v5/market/instruments-info?category=linear"
        response = requests.get(url, proxies=proxies, timeout=30)
        data = response.json()

        if data.get("retCode") != 0:
            log(f"API错误: {data.get('retMsg')}")
            return []

        instruments = data.get("result", {}).get("list", [])
        return instruments
    except Exception as e:
        log(f"获取instruments失败: {e}")
        return []

def get_bybit_tickers():
    """获取Bybit所有交易对的24h数据"""
    try:
        proxies = {
            "http": "http://127.0.0.1:18080",
            "https": "http://127.0.0.1:18080"
        }
        url = "https://api.bybit.com/v5/market/tickers?category=linear"
        response = requests.get(url, proxies=proxies, timeout=30)
        data = response.json()

        if data.get("retCode") != 0:
            log(f"API错误: {data.get('retMsg')}")
            return {}

        tickers = data.get("result", {}).get("list", [])
        # 转换为字典，以symbol为key
        return {t.get("symbol"): t for t in tickers}
    except Exception as e:
        log(f"获取tickers失败: {e}")
        return {}

def filter_and_sort_pairs(instruments, tickers_dict):
    """筛选和排序交易对 - 只选择支持合约的交易对"""
    priority_pairs = []
    other_pairs = []
    meme_pairs = []

    for inst in instruments:
        symbol = inst.get("symbol", "")

        # 只选择USDT交易对
        if not symbol.endswith("USDT"):
            continue

        # 检查是否是永续合约 (LinearPerpetual)
        contract_type = inst.get("contractType", "")
        if contract_type != "LinearPerpetual":
            continue

        # 检查交易状态
        if inst.get("status") != "Trading":
            continue

        # 跳过特殊格式的交易对 (如 1000000BABYDOGEUSDT)
        if symbol.startswith("1000") or symbol.startswith("10000") or symbol.startswith("0"):
            continue

        # 跳过黑名单
        base_coin = inst.get("baseCoin", symbol.replace("USDT", ""))
        pair = f"{base_coin}/USDT:USDT"
        if pair in BLACKLIST:
            continue

        # 从tickers获取交易量
        ticker = tickers_dict.get(symbol, {})
        turnover = float(ticker.get("turnover24h", 0) or 0)

        if turnover < MIN_VOLUME_USDT:
            continue

        # 检查杠杆设置（确保支持做多做空）
        leverage_filter = inst.get("leverageFilter", {})
        max_leverage = float(leverage_filter.get("maxLeverage", 0) or 0)
        if max_leverage < 1:
            continue  # 不支持杠杆

        pair_data = {
            "pair": pair,
            "volume": turnover,
            "max_leverage": max_leverage,
            "contract_type": contract_type,
            "base_coin": base_coin
        }

        # 分类：主流币优先
        if base_coin in PRIORITY_COINS:
            priority_pairs.append(pair_data)
        elif base_coin in MEME_COINS:
            meme_pairs.append(pair_data)
        else:
            other_pairs.append(pair_data)

    # 按交易量排序
    priority_pairs.sort(key=lambda x: x["volume"], reverse=True)
    other_pairs.sort(key=lambda x: x["volume"], reverse=True)
    meme_pairs.sort(key=lambda x: x["volume"], reverse=True)

    # 合并结果：主流币优先，然后是其他币，最后限制meme币数量
    # 最多选2个meme币
    result = priority_pairs + other_pairs + meme_pairs[:2]
    result.sort(key=lambda x: x["volume"], reverse=True)

    return result

def get_top_pairs(pairs, n=15):
    """获取前N个交易对"""
    # 优先选择主流币
    priority_coins = ["BTC", "ETH", "SOL", "XRP", "BNB", "DOGE", "AVAX", "LINK", "MATIC", "ARB", "OP", "ATOM", "LTC", "NEAR", "FIL", "INJ", "SUI", "WIF", "AAVE", "APT"]

    selected = []
    others = []

    for p in pairs:
        symbol = p["pair"].split("/")[0]
        if symbol in priority_coins:
            selected.append(p)
        else:
            others.append(p)

    # 合并，优先主流币
    result = selected + others
    return result[:n]

def update_config(new_pairs):
    """更新配置文件"""
    try:
        with open(CONFIG_PATH, "r") as f:
            config = json.load(f)

        old_pairs = config.get("exchange", {}).get("pair_whitelist", [])

        # 更新交易对列表
        config["exchange"]["pair_whitelist"] = new_pairs

        # 写入配置文件
        with open(CONFIG_PATH, "w") as f:
            json.dump(config, f, indent=2)

        log(f"配置已更新:")
        log(f"  旧交易对: {old_pairs}")
        log(f"  新交易对: {new_pairs}")

        return True
    except Exception as e:
        log(f"更新配置失败: {e}")
        return False

def main():
    log("=" * 50)
    log("开始更新动态交易对...")

    # 获取合约交易对信息
    instruments = get_bybit_instruments()
    if not instruments:
        log("无法获取合约交易对数据，保持原配置")
        return
    log(f"获取到 {len(instruments)} 个合约交易对")

    # 获取24h交易量数据
    tickers_dict = get_bybit_tickers()
    log(f"获取到 {len(tickers_dict)} 个ticker数据")

    # 筛选和排序
    filtered_pairs = filter_and_sort_pairs(instruments, tickers_dict)
    log(f"筛选后剩余 {len(filtered_pairs)} 个支持合约的交易对")

    # 获取Top N
    top_pairs = filtered_pairs[:TOP_N_PAIRS]
    pair_list = [p["pair"] for p in top_pairs]

    log(f"选择的交易对 (支持做多做空):")
    for p in top_pairs:
        log(f"  {p['pair']}: 交易量={p['volume']/1e6:.2f}M, 最大杠杆={p['max_leverage']}x")

    # 更新配置
    if pair_list:
        update_config(pair_list)
    else:
        log("没有符合条件的交易对，保持原配置")

    log("更新完成")

if __name__ == "__main__":
    main()