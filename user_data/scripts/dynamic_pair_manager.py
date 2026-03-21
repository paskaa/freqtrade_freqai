#!/usr/bin/env python3
"""
动态交易对管理器
集成freqtrade，实现舆情驱动的交易对自动扩展
"""

import os
import sys
import json
import time
import logging
import asyncio
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Optional, Set

# 添加路径
sys.path.insert(0, str(Path(__file__).parent))

from dynamic_pair_discovery import DynamicPairDiscovery, get_discovery

logger = logging.getLogger(__name__)

# 全局动态交易对存储
DYNAMIC_PAIRS_FILE = Path("/root/ft_userdata/user_data/scripts/dynamic_pairs.json")
DYNAMIC_PAIRS: Dict[str, dict] = {}
_last_pair_update = None


class DynamicPairManager:
    """动态交易对管理器"""

    def __init__(self, config_path: str, strategy_instance=None):
        self.config_path = config_path
        self.strategy = strategy_instance
        self.discovery = DynamicPairDiscovery()
        self.running = False
        self.update_interval = 300  # 5分钟更新一次
        self.max_dynamic_pairs = 10  # 最多动态添加的交易对数量
        self.min_score_threshold = 0.6  # 最低热门得分阈值

        # 加载已有的动态交易对
        self.load_dynamic_pairs()

    def load_dynamic_pairs(self):
        """加载动态交易对"""
        global DYNAMIC_PAIRS
        if DYNAMIC_PAIRS_FILE.exists():
            try:
                with open(DYNAMIC_PAIRS_FILE, 'r') as f:
                    DYNAMIC_PAIRS = json.load(f)
                logger.info(f"加载 {len(DYNAMIC_PAIRS)} 个动态交易对")
            except Exception as e:
                logger.warning(f"加载动态交易对失败: {e}")

    def save_dynamic_pairs(self):
        """保存动态交易对"""
        global DYNAMIC_PAIRS
        try:
            with open(DYNAMIC_PAIRS_FILE, 'w') as f:
                json.dump(DYNAMIC_PAIRS, f, indent=2)
        except Exception as e:
            logger.warning(f"保存动态交易对失败: {e}")

    def get_static_pairs(self) -> List[str]:
        """获取配置文件中的静态交易对"""
        try:
            with open(self.config_path, 'r') as f:
                config = json.load(f)
            return config.get('exchange', {}).get('pair_whitelist', [])
        except Exception as e:
            logger.error(f"读取配置文件失败: {e}")
            return []

    def add_pair_to_config(self, pair: str) -> bool:
        """添加交易对到配置文件"""
        try:
            with open(self.config_path, 'r') as f:
                config = json.load(f)

            current_pairs = config.get('exchange', {}).get('pair_whitelist', [])

            if pair not in current_pairs:
                current_pairs.append(pair)
                config['exchange']['pair_whitelist'] = current_pairs

                with open(self.config_path, 'w') as f:
                    json.dump(config, f, indent=2)

                logger.info(f"✅ 添加交易对到配置: {pair}")
                return True
            return False
        except Exception as e:
            logger.error(f"添加交易对失败: {e}")
            return False

    def remove_pair_from_config(self, pair: str) -> bool:
        """从配置文件移除交易对"""
        try:
            with open(self.config_path, 'r') as f:
                config = json.load(f)

            current_pairs = config.get('exchange', {}).get('pair_whitelist', [])

            if pair in current_pairs:
                current_pairs.remove(pair)
                config['exchange']['pair_whitelist'] = current_pairs

                with open(self.config_path, 'w') as f:
                    json.dump(config, f, indent=2)

                logger.info(f"移除交易对: {pair}")
                return True
            return False
        except Exception as e:
            logger.error(f"移除交易对失败: {e}")
            return False

    async def check_exchange_support(self, symbol: str) -> bool:
        """检查交易所是否支持该交易对"""
        try:
            import ccxt
            exchange = ccxt.bitget({
                'enableRateLimit': True,
            })

            # 刷新市场数据
            await asyncio.to_thread(exchange.load_markets)

            # 检查合约
            futures_pair = f"{symbol}/USDT:USDT"
            if futures_pair in exchange.markets:
                return True

            # 检查现货
            spot_pair = f"{symbol}/USDT"
            if spot_pair in exchange.markets:
                return True

            return False
        except Exception as e:
            logger.warning(f"检查交易所支持失败: {e}")
            # 出错时假设支持，让交易时再验证
            return True

    async def discover_and_add_pairs(self) -> List[str]:
        """发现并添加新的交易对"""
        global DYNAMIC_PAIRS, _last_pair_update

        now = datetime.now()

        # 检查更新间隔
        if _last_pair_update and (now - _last_pair_update).total_seconds() < self.update_interval:
            return []

        logger.info("🔍 开始发现新交易对...")

        # 获取热门交易对
        discovered = await self.discovery.discover_new_pairs()

        # 获取当前已配置的交易对
        static_pairs = self.get_static_pairs()
        static_symbols = set()
        for pair in static_pairs:
            symbol = pair.split('/')[0].replace(':USDT', '')
            static_symbols.add(symbol)

        # 筛选新的可交易对
        new_pairs = []
        for symbol, data in sorted(discovered.items(),
                                   key=lambda x: x[1].get('score', 0),
                                   reverse=True):

            # 检查是否已存在
            if symbol in static_symbols:
                continue

            # 检查得分阈值
            if data.get('score', 0) < self.min_score_threshold:
                continue

            # 检查交易所支持
            exchange_supported = await self.check_exchange_support(symbol)
            if not exchange_supported:
                logger.info(f"⏭️ {symbol} 交易所不支持，跳过")
                continue

            # 添加到动态列表
            pair = f"{symbol}/USDT:USDT"
            DYNAMIC_PAIRS[symbol] = {
                'pair': pair,
                'symbol': symbol,
                'score': data.get('score', 0),
                'source': data.get('source', ''),
                'added_at': now.isoformat(),
                'trades': 0,
                'pnl': 0.0
            }

            new_pairs.append(pair)
            logger.info(f"🔥 发现新热门: {symbol} (得分: {data.get('score', 0):.2f}, 来源: {data.get('source', '')})")

            # 限制数量
            if len(new_pairs) >= self.max_dynamic_pairs:
                break

        # 保存动态交易对
        self.save_dynamic_pairs()
        _last_pair_update = now

        return new_pairs

    def get_all_tradable_pairs(self) -> List[str]:
        """获取所有可交易对 (静态 + 动态)"""
        static_pairs = self.get_static_pairs()

        # 添加动态交易对
        all_pairs = list(static_pairs)
        for symbol, data in DYNAMIC_PAIRS.items():
            pair = data.get('pair', f"{symbol}/USDT:USDT")
            if pair not in all_pairs:
                all_pairs.append(pair)

        return all_pairs

    def is_dynamic_pair(self, pair: str) -> bool:
        """检查是否为动态添加的交易对"""
        symbol = pair.split('/')[0].replace(':USDT', '')
        return symbol in DYNAMIC_PAIRS

    def update_pair_performance(self, pair: str, pnl: float):
        """更新交易对表现"""
        symbol = pair.split('/')[0].replace(':USDT', '')

        if symbol in DYNAMIC_PAIRS:
            DYNAMIC_PAIRS[symbol]['trades'] = DYNAMIC_PAIRS[symbol].get('trades', 0) + 1
            DYNAMIC_PAIRS[symbol]['pnl'] = DYNAMIC_PAIRS[symbol].get('pnl', 0) + pnl
            DYNAMIC_PAIRS[symbol]['last_trade'] = datetime.now().isoformat()
            self.save_dynamic_pairs()

    def cleanup_underperforming_pairs(self):
        """清理表现不佳的动态交易对"""
        global DYNAMIC_PAIRS

        to_remove = []
        for symbol, data in DYNAMIC_PAIRS.items():
            # 如果交易超过5次且累计亏损超过阈值
            if data.get('trades', 0) > 5 and data.get('pnl', 0) < -0.05:
                to_remove.append(symbol)
                logger.info(f"移除表现不佳的交易对: {symbol}")

        for symbol in to_remove:
            del DYNAMIC_PAIRS[symbol]

        if to_remove:
            self.save_dynamic_pairs()

    def start_background_discovery(self):
        """启动后台发现任务"""
        self.running = True

        def discovery_loop():
            while self.running:
                try:
                    # 运行发现
                    asyncio.run(self.discover_and_add_pairs())

                    # 清理表现不佳的
                    self.cleanup_underperforming_pairs()

                except Exception as e:
                    logger.error(f"发现任务异常: {e}")

                # 等待下次更新
                time.sleep(self.update_interval)

        thread = threading.Thread(target=discovery_loop, daemon=True)
        thread.start()
        logger.info("✅ 后台发现任务已启动")

    def stop(self):
        """停止后台任务"""
        self.running = False


# 便捷函数
_manager_instance = None

def get_manager(config_path: str = None) -> DynamicPairManager:
    """获取管理器实例"""
    global _manager_instance
    if _manager_instance is None and config_path:
        _manager_instance = DynamicPairManager(config_path)
    return _manager_instance


def get_dynamic_pairs() -> List[str]:
    """获取动态交易对列表"""
    return [data.get('pair') for data in DYNAMIC_PAIRS.values()]


def is_tradable_pair(pair: str) -> bool:
    """检查交易对是否可交易"""
    symbol = pair.split('/')[0].replace(':USDT', '')
    # 检查是否在动态列表中
    if symbol in DYNAMIC_PAIRS:
        return True
    return False


def record_trade_result(pair: str, pnl: float):
    """记录交易结果"""
    symbol = pair.split('/')[0].replace(':USDT', '')
    if symbol in DYNAMIC_PAIRS:
        DYNAMIC_PAIRS[symbol]['trades'] = DYNAMIC_PAIRS[symbol].get('trades', 0) + 1
        DYNAMIC_PAIRS[symbol]['pnl'] = DYNAMIC_PAIRS[symbol].get('pnl', 0) + pnl
        DYNAMIC_PAIRS[symbol]['last_trade'] = datetime.now().isoformat()

        # 保存
        try:
            with open(DYNAMIC_PAIRS_FILE, 'w') as f:
                json.dump(DYNAMIC_PAIRS, f, indent=2)
        except:
            pass


# 测试
if __name__ == "__main__":
    async def test():
        config_path = "/root/ft_userdata/user_data/config_trade_15m.json"
        manager = DynamicPairManager(config_path)

        print("\n" + "="*60)
        print("当前静态交易对:")
        print("="*60)
        for pair in manager.get_static_pairs():
            print(f"  - {pair}")

        print("\n" + "="*60)
        print("发现新交易对...")
        print("="*60)

        new_pairs = await manager.discover_and_add_pairs()

        print("\n" + "="*60)
        print("所有可交易对:")
        print("="*60)
        for pair in manager.get_all_tradable_pairs():
            is_dynamic = "🔥" if manager.is_dynamic_pair(pair) else "  "
            print(f"{is_dynamic} {pair}")

    asyncio.run(test())