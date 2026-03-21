#!/usr/bin/env python3
"""
动态交易对发现服务
定时发现热门交易对并更新freqtrade配置
"""

import asyncio
import json
import logging
import os
import sys
import time
import signal
from datetime import datetime
from pathlib import Path

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('/root/ft_userdata/user_data/logs/dynamic_pair_service.log')
    ]
)
logger = logging.getLogger(__name__)

# 添加路径
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, '/root/ft_userdata/user_data/strategies')

from dynamic_pair_discovery import DynamicPairDiscovery

# 配置
CONFIG_PATH = Path("/root/ft_userdata/user_data/config_trade_15m.json")
FREQTRADE_PID_FILE = Path("/root/ft_userdata/user_data/freqtrade.pid")
MAX_DYNAMIC_PAIRS = 10
UPDATE_INTERVAL = 300  # 5分钟
MIN_SCORE_THRESHOLD = 0.5


class DynamicPairService:
    """动态交易对发现服务"""

    def __init__(self):
        self.discovery = DynamicPairDiscovery()
        self.running = True
        self.last_update = None
        self.known_pairs = set()

        # 加载已知交易对
        self._load_known_pairs()

        # 信号处理
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _signal_handler(self, signum, frame):
        """信号处理器"""
        logger.info(f"收到信号 {signum}, 停止服务...")
        self.running = False

    def _load_known_pairs(self):
        """加载已知交易对"""
        try:
            with open(CONFIG_PATH, 'r') as f:
                config = json.load(f)
            self.known_pairs = set(config.get('exchange', {}).get('pair_whitelist', []))
            logger.info(f"加载 {len(self.known_pairs)} 个已知交易对")
        except Exception as e:
            logger.error(f"加载配置失败: {e}")
            self.known_pairs = set()

    def _check_exchange_support(self, symbol: str) -> bool:
        """检查交易所是否支持该交易对"""
        try:
            import ccxt
            exchange = ccxt.bitget({
                'enableRateLimit': True,
                'proxies': {
                    'http': 'http://127.0.0.1:18080',
                    'https': 'http://127.0.0.1:18080'
                }
            })
            exchange.load_markets()

            # 检查合约
            futures_pair = f"{symbol}/USDT:USDT"
            if futures_pair in exchange.markets:
                logger.info(f"✅ {symbol} 在交易所支持")
                return True

            # 检查是否有其他格式的交易对
            for pair in exchange.markets:
                if symbol.upper() in pair and 'USDT' in pair:
                    logger.info(f"✅ {symbol} 找到交易对: {pair}")
                    return True

            logger.info(f"❌ {symbol} 交易所不支持")
            return False
        except Exception as e:
            logger.warning(f"检查交易所支持失败 {symbol}: {e}")
            return True  # 假设支持

    def _update_config(self, new_pairs: list) -> bool:
        """更新配置文件"""
        try:
            with open(CONFIG_PATH, 'r') as f:
                config = json.load(f)

            current_pairs = config.get('exchange', {}).get('pair_whitelist', [])

            # 添加新交易对
            added = 0
            for pair in new_pairs:
                if pair not in current_pairs:
                    current_pairs.append(pair)
                    added += 1
                    logger.info(f"✅ 添加交易对: {pair}")

            if added > 0:
                config['exchange']['pair_whitelist'] = current_pairs

                # 备份原配置
                backup_path = CONFIG_PATH.with_suffix('.json.bak')
                with open(backup_path, 'w') as f:
                    json.dump(config, f, indent=2)

                # 写入新配置
                with open(CONFIG_PATH, 'w') as f:
                    json.dump(config, f, indent=2)

                logger.info(f"配置已更新, 添加 {added} 个交易对")
                return True

            return False
        except Exception as e:
            logger.error(f"更新配置失败: {e}")
            return False

    def _restart_freqtrade(self):
        """重启freqtrade以加载新配置"""
        try:
            # 发送信号让freqtrade重新加载
            # 注意：freqtrade可能不支持热重载，需要重启
            logger.info("尝试重启freqtrade...")

            # 方法1: 使用pkill发送SIGHUP (如果支持热重载)
            # os.system("pkill -HUP -f 'freqtrade trade'")

            # 方法2: 完全重启 (更可靠)
            os.system("pkill -f 'freqtrade trade'")
            time.sleep(2)

            # 启动新的freqtrade进程
            cmd = (
                "cd /root/ft_userdata && "
                "nohup .venv/bin/freqtrade trade "
                "--logfile /root/ft_userdata/user_data/logs/freqtrade.log "
                "--config /root/ft_userdata/user_data/config_trade_15m.json "
                "--strategy Alvinchen_15m131 > /dev/null 2>&1 &"
            )
            os.system(cmd)

            logger.info("✅ Freqtrade已重启")
            time.sleep(5)
        except Exception as e:
            logger.error(f"重启freqtrade失败: {e}")

    async def discover_and_update(self):
        """发现并更新交易对"""
        logger.info("🔍 开始发现新交易对...")

        try:
            # 发现热门交易对
            discovered = await self.discovery.discover_new_pairs()

            # 筛选可交易的新交易对
            new_pairs = []
            for symbol, data in sorted(discovered.items(),
                                       key=lambda x: x[1].get('score', 0),
                                       reverse=True):

                # 检查得分
                if data.get('score', 0) < MIN_SCORE_THRESHOLD:
                    continue

                pair = f"{symbol}/USDT:USDT"

                # 检查是否已存在
                if pair in self.known_pairs:
                    continue

                # 检查交易所支持
                if self._check_exchange_support(symbol):
                    new_pairs.append(pair)
                    self.known_pairs.add(pair)

                    logger.info(f"🔥 发现热门: {symbol} "
                              f"(得分: {data.get('score', 0):.2f}, "
                              f"来源: {data.get('source', '')})")

                    if len(new_pairs) >= MAX_DYNAMIC_PAIRS:
                        break

            # 更新配置
            if new_pairs:
                if self._update_config(new_pairs):
                    # 重启freqtrade
                    self._restart_freqtrade()

            self.last_update = datetime.now()
            logger.info(f"发现完成, 新增 {len(new_pairs)} 个交易对")

        except Exception as e:
            logger.error(f"发现过程出错: {e}", exc_info=True)

    async def run(self):
        """主运行循环"""
        logger.info("="*60)
        logger.info("🚀 动态交易对发现服务启动")
        logger.info(f"配置文件: {CONFIG_PATH}")
        logger.info(f"更新间隔: {UPDATE_INTERVAL}秒")
        logger.info(f"最大动态交易对: {MAX_DYNAMIC_PAIRS}")
        logger.info("="*60)

        while self.running:
            try:
                await self.discover_and_update()

                # 等待下次更新
                for _ in range(UPDATE_INTERVAL):
                    if not self.running:
                        break
                    await asyncio.sleep(1)

            except Exception as e:
                logger.error(f"运行异常: {e}")
                await asyncio.sleep(60)

        logger.info("服务停止")


async def main():
    """主入口"""
    service = DynamicPairService()
    await service.run()


if __name__ == "__main__":
    asyncio.run(main())