#!/usr/bin/env python3
"""
动态交易对发现模块
基于舆情追踪自动发现热门交易对
"""

import asyncio
import aiohttp
import logging
import re
import json
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set
from collections import defaultdict
from pathlib import Path

logger = logging.getLogger(__name__)

class DynamicPairDiscovery:
    """动态交易对发现器"""

    def __init__(self, exchange_api=None):
        self.exchange_api = exchange_api
        self.cache_file = Path("/root/ft_userdata/user_data/scripts/discovered_pairs.json")
        self.discovered_pairs: Dict[str, dict] = {}
        self.trending_scores: Dict[str, float] = {}
        self.last_update = None
        self.update_interval = 300  # 5分钟更新一次

        # 已知币种映射 (符号 -> 全名)
        self.known_symbols = {
            'btc': 'BTC', 'bitcoin': 'BTC',
            'eth': 'ETH', 'ethereum': 'ETH',
            'sol': 'SOL', 'solana': 'SOL',
            'xrp': 'XRP', 'ripple': 'XRP',
            'doge': 'DOGE', 'dogecoin': 'DOGE',
            'ada': 'ADA', 'cardano': 'ADA',
            'avax': 'AVAX', 'avalanche': 'AVAX',
            'link': 'LINK', 'chainlink': 'LINK',
            'dot': 'DOT', 'polkadot': 'DOT',
            'matic': 'MATIC', 'polygon': 'MATIC',
            'arb': 'ARB', 'arbitrum': 'ARB',
            'op': 'OP', 'optimism': 'OP',
            'atom': 'ATOM', 'cosmos': 'ATOM',
            'ltc': 'LTC', 'litecoin': 'LTC',
            'near': 'NEAR',
            'fil': 'FIL', 'filecoin': 'FIL',
            'inj': 'INJ', 'injective': 'INJ',
            'sui': 'SUI',
            'wld': 'WLD', 'worldcoin': 'WLD',
            'pepe': 'PEPE',
            'shib': 'SHIB', 'shiba': 'SHIB',
            'bonk': 'BONK',
            'wif': 'WIF',
            'floki': 'FLOKI',
            'bome': 'BOME',
            'ondo': 'ONDO',
            'jup': 'JUP', 'jupiter': 'JUP',
            'pyth': 'PYTH',
            'strk': 'STRK', 'starknet': 'STRK',
            'aevo': 'AEVO',
            'ena': 'ENA',
            'w': 'W', 'wormhole': 'W',
            'tiao': 'TIA', 'celestia': 'TIA',
            'sei': 'SEI',
            'sag': 'SAGA', 'saga': 'SAGA',
            'mem': 'MEME',
            'brett': 'BRETT',
            'aer': 'AERO', 'aerodrome': 'AERO',
            'pendle': 'PENDLE',
            'ez': 'EZETH', 'ezeth': 'EZETH',
            'ethfi': 'ETHFI', 'etherfi': 'ETHFI',
            'eigen': 'EIGEN', 'eigenda': 'EIGEN',
            'kmno': 'KMNO', 'kamino': 'KMNO',
            'zro': 'ZRO', 'layerzero': 'ZRO',
            'zku': 'ZK', 'zksync': 'ZK',
            'manta': 'MANTA',
            'dym': 'DYME', 'dymension': 'DYM',
            'sac': 'SACRA', 'sacra': 'SACRA',
            # 新增新闻常见币种
            'trump': 'TRUMP',
            'ai16z': 'AI16Z',
            'virtual': 'VIRTUAL',
            'pengu': 'PENGU',
            'hype': 'HYPE',
            'pi': 'PI',
            'kas': 'KAS', 'kaspa': 'KAS',
            'aster': 'ASTER',
            'zec': 'ZEC', 'zcash': 'ZEC',
            'bard': 'BARD',
            'bnb': 'BNB', 'binance': 'BNB',
            'ton': 'TON', 'toncoin': 'TON',
            'apt': 'APT', 'aptos': 'APT',
            'move': 'MOVE', 'movement': 'MOVE',
            'bera': 'BERA', 'berachain': 'BERA',
            'hyper': 'HYPE', 'hyperliquid': 'HYPE',
            'render': 'RNDR', 'rndr': 'RNDR',
            'fet': 'FET', 'fetch': 'FET',
            'agix': 'AGIX',
            'tao': 'TAO', 'bittensor': 'TAO',
            'aave': 'AAVE',
            'uni': 'UNI', 'uniswap': 'UNI',
            'mkraw': 'MKR', 'maker': 'MKR',
            'crv': 'CRV', 'curve': 'CRV',
            'ldo': 'LDO', 'lido': 'LDO',
            'rocket': 'RPL', 'rpl': 'RPL',
            'gmx': 'GMX',
            'dydx': 'DYDX',
            'blur': 'BLUR',
            'ape': 'APE', 'apecoin': 'APE',
            'memo': 'MEME', 'meme': 'MEME',
            'boden': 'BODEN',
            'tremp': 'TREMP',
            'mother': 'MOTHER',
            'daddy': 'DADDY',
            'igor': 'IGOR',
            'michi': 'MICHI',
            'popcat': 'POPCAT',
            'meow': 'MEW',
            'nap': 'NAP',
            'myro': 'MYRO',
            'wenc': 'WEN', 'wen': 'WEN',
            'nft': None,  # NFT不是币种
        }

        # 移除None值
        self.known_symbols = {k: v for k, v in self.known_symbols.items() if v is not None}

        # 热门关键词权重
        self.keyword_weights = {
            'pump': 2.0,
            'moon': 1.5,
            'bullish': 1.5,
            'breakout': 1.3,
            'surge': 1.3,
            'rally': 1.2,
            'buy': 1.0,
            'long': 1.0,
            'hot': 1.0,
            'trending': 1.5,
            'gem': 1.2,
            'alpha': 1.3,
            'launch': 1.5,
            'new': 1.0,
            'airdrop': 1.5,
        }

        self.load_cache()

    def load_cache(self):
        """加载缓存"""
        if self.cache_file.exists():
            try:
                with open(self.cache_file, 'r') as f:
                    data = json.load(f)
                    self.discovered_pairs = data.get('discovered_pairs', {})
                    self.trending_scores = data.get('trending_scores', {})
                logger.info(f"加载缓存: {len(self.discovered_pairs)} 个已发现交易对")
            except Exception as e:
                logger.warning(f"加载缓存失败: {e}")

    def save_cache(self):
        """保存缓存"""
        try:
            with open(self.cache_file, 'w') as f:
                json.dump({
                    'discovered_pairs': self.discovered_pairs,
                    'trending_scores': self.trending_scores,
                    'last_update': datetime.now().isoformat()
                }, f, indent=2)
        except Exception as e:
            logger.warning(f"保存缓存失败: {e}")

    async def fetch_coingecko_trending(self) -> List[dict]:
        """获取CoinGecko热门币种"""
        try:
            async with aiohttp.ClientSession() as session:
                url = "https://api.coingecko.com/api/v3/search/trending"
                proxy = "http://127.0.0.1:18080"
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=15),
                                       proxy=proxy) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        coins = []
                        for item in data.get('coins', [])[:20]:
                            coin = item.get('item', {})
                            coins.append({
                                'symbol': coin.get('symbol', '').upper(),
                                'name': coin.get('name', ''),
                                'market_cap_rank': coin.get('market_cap_rank', 999),
                                'score': coin.get('score', 0),
                                'source': 'coingecko_trending'
                            })
                        return coins
        except Exception as e:
            logger.warning(f"获取CoinGecko热门失败: {e}")
        return []

    async def fetch_coingecko_top_gainers(self) -> List[dict]:
        """获取CoinGecko涨幅榜"""
        try:
            async with aiohttp.ClientSession() as session:
                url = "https://api.coingecko.com/api/v3/coins/markets"
                params = {
                    'vs_currency': 'usd',
                    'order': 'price_change_percentage_24h_desc',
                    'per_page': 30,
                    'page': 1,
                    'sparkline': 'false'
                }
                proxy = "http://127.0.0.1:18080"
                async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=15),
                                       proxy=proxy) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        coins = []
                        for coin in data:
                            change = coin.get('price_change_percentage_24h', 0) or 0
                            if change > 5:  # 涨幅超过5%
                                coins.append({
                                    'symbol': coin.get('symbol', '').upper(),
                                    'name': coin.get('name', ''),
                                    'price_change_24h': change,
                                    'market_cap_rank': coin.get('market_cap_rank', 999),
                                    'source': 'coingecko_gainers'
                                })
                        return coins
        except Exception as e:
            logger.warning(f"获取涨幅榜失败: {e}")
        return []

    async def fetch_twitter_trending(self) -> List[dict]:
        """从Twitter/X追踪热门话题 (模拟)"""
        # 实际实现需要Twitter API或爬虫
        # 这里使用预设的热门话题模拟
        trending_topics = []

        # 模拟从Twitter获取的热门币种
        # 实际可以接入Twitter API v2或使用其他数据源
        mock_trending = [
            {'symbol': 'PEPE', 'mentions': 5000, 'sentiment': 0.7},
            {'symbol': 'WIF', 'mentions': 3000, 'sentiment': 0.6},
            {'symbol': 'BONK', 'mentions': 2500, 'sentiment': 0.65},
            {'symbol': 'FLOKI', 'mentions': 2000, 'sentiment': 0.55},
            {'symbol': 'SHIB', 'mentions': 4000, 'sentiment': 0.5},
            {'symbol': 'DOGE', 'mentions': 6000, 'sentiment': 0.6},
            {'symbol': 'TRUMP', 'mentions': 3500, 'sentiment': 0.8},
            {'symbol': 'AI16Z', 'mentions': 2000, 'sentiment': 0.7},
            {'symbol': 'VIRTUAL', 'mentions': 1800, 'sentiment': 0.65},
            {'symbol': 'PENGU', 'mentions': 1500, 'sentiment': 0.6},
        ]

        for item in mock_trending:
            trending_topics.append({
                'symbol': item['symbol'],
                'mentions': item['mentions'],
                'sentiment': item['sentiment'],
                'source': 'twitter_trending'
            })

        return trending_topics

    async def fetch_fallback_trending(self) -> List[dict]:
        """备用热门币种列表 (当API不可用时)"""
        # 基于市场热点手动维护
        trending = [
            {'symbol': 'PEPE', 'score': 0.9, 'source': 'fallback'},
            {'symbol': 'WIF', 'score': 0.85, 'source': 'fallback'},
            {'symbol': 'BONK', 'score': 0.8, 'source': 'fallback'},
            {'symbol': 'TRUMP', 'score': 0.85, 'source': 'fallback'},
            {'symbol': 'AI16Z', 'score': 0.75, 'source': 'fallback'},
            {'symbol': 'VIRTUAL', 'score': 0.7, 'source': 'fallback'},
            {'symbol': 'FLOKI', 'score': 0.65, 'source': 'fallback'},
            {'symbol': 'SHIB', 'score': 0.6, 'source': 'fallback'},
            {'symbol': '1000PEPE', 'score': 0.55, 'source': 'fallback'},  # Bitget格式
            {'symbol': 'MEME', 'score': 0.5, 'source': 'fallback'},
        ]
        return trending

    async def fetch_dexscreener_trending(self) -> List[dict]:
        """获取DexScreener热门代币"""
        try:
            async with aiohttp.ClientSession() as session:
                url = "https://api.dexscreener.com/token-boosts/top/v1"
                proxy = "http://127.0.0.1:18080"
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=10),
                                       proxy=proxy) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        coins = []
                        for item in data[:20]:
                            base_token = item.get('baseToken', {})
                            symbol = base_token.get('symbol', '').upper()
                            if symbol and len(symbol) <= 10:  # 过滤异常长名称
                                coins.append({
                                    'symbol': symbol,
                                    'name': base_token.get('name', ''),
                                    'chain': item.get('chainId', ''),
                                    'url': item.get('url', ''),
                                    'source': 'dexscreener'
                                })
                        return coins
        except Exception as e:
            logger.warning(f"获取DexScreener热门失败: {e}")
        return []

    async def fetch_binance_new_listings(self) -> List[dict]:
        """获取Binance新上线币种"""
        try:
            async with aiohttp.ClientSession() as session:
                url = "https://www.binance.com/bapi/composite/v1/public/cms/article/list/query"
                params = {"type": 1, "catalogId": 48, "page": 1, "pageSize": 10}
                proxy = "http://127.0.0.1:18080"
                async with session.post(url, json=params, timeout=aiohttp.ClientTimeout(total=10),
                                        proxy=proxy) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        coins = []
                        articles = data.get('data', {}).get('articles', [])
                        for article in articles[:5]:
                            title = article.get('title', '')
                            # 从标题提取币种符号
                            matches = re.findall(r'\b([A-Z]{2,10})\b', title)
                            for symbol in matches:
                                if symbol not in ['Binance', 'Will', 'The', 'New', 'Listing']:
                                    coins.append({
                                        'symbol': symbol,
                                        'title': title,
                                        'release_date': article.get('releaseDate', 0),
                                        'source': 'binance_new_listing'
                                    })
                        return coins
        except Exception as e:
            logger.warning(f"获取Binance新币失败: {e}")
        return []

    async def fetch_cointelegraph_news(self) -> List[dict]:
        """获取Cointelegraph新闻热点"""
        try:
            async with aiohttp.ClientSession() as session:
                url = "https://cointelegraph.com/rss"
                proxy = "http://127.0.0.1:18080"
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=15),
                                       proxy=proxy) as resp:
                    if resp.status == 200:
                        content = await resp.text()
                        coins = []
                        root = ET.fromstring(content)
                        items = root.findall('.//item')[:30]

                        # 非币种词过滤
                        exclude_words = {'THE', 'AND', 'FOR', 'NEW', 'FROM', 'WITH',
                                       'THIS', 'THAT', 'NEWS', 'WILL', 'ARE', 'HAS',
                                       'HIS', 'HER', 'BUT', 'NOT', 'YOU', 'ALL', 'CAN',
                                       'CEO', 'SEC', 'FTX', 'SBI', 'UK', 'US', 'EU',
                                       'FED', 'ETF', 'NFT', 'AI', 'IRS', 'NY', 'DC',
                                       'VC', 'FEATURES', 'PPI', 'FOMC', 'GDP', 'CPI',
                                       'DEA', 'FDA', 'DOJ', 'FBI', 'CIA', 'NSA',
                                       'AMA', 'FAQ', 'PDF', 'API', 'SDK', 'IOS',
                                       'Q1', 'Q2', 'Q3', 'Q4', 'YTD', 'MTD',
                                       # 更多非币种词
                                       'MARKETS', 'OPINION', 'IPO', 'DAO', 'PROTOCOL',
                                       'PLATFORM', 'EXCHANGE', 'WALLET', 'TOKEN', 'COIN',
                                       'TRADING', 'MARKET', 'PRICE', 'CHAIN', 'NETWORK',
                                       'LAUNCH', 'UPDATE', 'REPORT', 'ANALYSIS', 'DATA',
                                       'TODAY', 'WEEK', 'MONTH', 'YEAR', 'TIME', 'LIVE',
                                       'BREAKING', 'LATEST', 'ALERT', 'WATCH', 'REVIEW',
                                       # 新增常见假阳性词
                                       'CNY', 'VOLATILITY', 'ADJUSTS', 'EAST', 'DOLLAR',
                                       'TENSIONS', 'ON', 'OIL', 'SURGE', 'PRICES', 'CANADIAN',
                                       'ESCALATING', 'SOARS', 'MIDDLE', 'WHALE', 'SIGNALS',
                                       'MILLION', 'SHIFT', 'PURCHASE', 'MAJOR', 'AT', 'LNG',
                                       'FORCE', 'QATAR', 'MAJEURE', 'CURBED', 'LAFFAN', 'RAS',
                                       'EXPORTS', 'ASSETS', 'BUY', 'DEFINES', 'CRYPTO',
                                       'AMID', 'OVER', 'AFTER', 'BEFORE', 'SINCE', 'UNTIL',
                                       'AGAINST', 'BETWEEN', 'THROUGH', 'DURING', 'WITHOUT',
                                       'WITHIN', 'ALONG', 'AMONG', 'ABOVE', 'BELOW',
                                       # 更多假阳性
                                       'FEES', 'ZERO', 'BEST', 'CALLS', 'RECENT', 'TRUTH',
                                       'CORRECTION', 'HEALTHY', 'RALLY', 'CRASH', 'PUMP',
                                       'DUMP', 'HIGH', 'LOW', 'GAIN', 'LOSS', 'RISE',
                                       'FALL', 'DROP', 'JUMP', 'SLIDE', 'DIP', 'TOP',
                                       # 更多假阳性
                                       'FINANCIAL', 'TOOL', 'VISA', 'LAUNCHES', 'AUTONOMOUS',
                                       'SOURCE', 'GET', 'MAKES', 'SAYS', 'WANTS', 'HELPS',
                                       'SHOWS', 'OFFERS', 'MEANS', 'NEEDS', 'LOOKS',
                                       'BOOST', 'PAYMENTS', 'DRIVEN', 'REVEALS', 'CRUCIAL'}

                        for item in items:
                            title_elem = item.find('title')
                            category_elems = item.findall('category')

                            if title_elem is not None:
                                title = title_elem.text or ''

                                # 从标题和分类提取币种符号
                                symbols_found = set()

                                # 从标题提取
                                title_matches = re.findall(r'\b([A-Z]{2,10})\b', title)
                                symbols_found.update(title_matches)

                                # 从分类提取
                                for cat in category_elems:
                                    if cat.text:
                                        cat_text = cat.text.upper()
                                        if cat_text in ['BITCOIN', 'BTC']:
                                            symbols_found.add('BTC')
                                        elif cat_text in ['ETHEREUM', 'ETH']:
                                            symbols_found.add('ETH')
                                        elif cat_text in ['SOLANA', 'SOL']:
                                            symbols_found.add('SOL')
                                        elif len(cat_text) >= 2 and len(cat_text) <= 10 and cat_text.isalpha():
                                            symbols_found.add(cat_text)

                                for symbol in symbols_found - exclude_words:
                                    coins.append({
                                        'symbol': symbol,
                                        'title': title,
                                        'categories': [c.text for c in category_elems if c.text],
                                        'source': 'cointelegraph'
                                    })

                        return coins
        except Exception as e:
            logger.warning(f"获取Cointelegraph新闻失败: {e}")
        return []

    async def fetch_coinmarketcap_news(self) -> List[dict]:
        """获取CoinMarketCap头条新闻"""
        try:
            async with aiohttp.ClientSession() as session:
                url = "https://coinmarketcap.com/headlines/news/"
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                    'Accept-Encoding': 'gzip, deflate'
                }
                proxy = "http://127.0.0.1:18080"
                async with session.get(url, headers=headers,
                                       timeout=aiohttp.ClientTimeout(total=15),
                                       proxy=proxy) as resp:
                    if resp.status == 200:
                        content = await resp.text()
                        coins = []

                        # 提取新闻标题中的币种
                        titles = re.findall(r'"title":"([^"]+)"', content)

                        for title in titles[:30]:
                            # 从标题提取币种符号
                            symbols_found = re.findall(r'\b([A-Z]{2,10})\b', title.upper())

                            # 特殊处理
                            if 'BITCOIN' in title.upper() or 'BTC' in title.upper():
                                symbols_found.append('BTC')
                            if 'ETHEREUM' in title.upper() or 'ETH' in title.upper():
                                symbols_found.append('ETH')
                            if 'SOLANA' in title.upper() or 'SOL' in title.upper():
                                symbols_found.append('SOL')

                            # 过滤常见非币种词
                            exclude_words = {'THE', 'AND', 'FOR', 'NEW', 'FROM', 'WITH',
                                           'THIS', 'THAT', 'NEWS', 'WILL', 'ARE', 'HAS',
                                           'BUT', 'NOT', 'YOU', 'ALL', 'CAN', 'AS', 'USD',
                                           'SEC', 'ETF', 'NFT', 'AI', 'GDP', 'PBOC', 'CEO',
                                           'UK', 'US', 'EU', 'FED', 'IMF', 'IRS', 'NY',
                                           'VC', 'FEATURES', 'PPI', 'FOMC', 'CPI',
                                           'MARKETS', 'OPINION', 'IPO', 'DAO', 'PROTOCOL',
                                           'PLATFORM', 'EXCHANGE', 'WALLET', 'TOKEN', 'COIN',
                                           'TRADING', 'MARKET', 'PRICE', 'CHAIN', 'NETWORK',
                                           'LAUNCH', 'UPDATE', 'REPORT', 'ANALYSIS', 'DATA',
                                           # 更多非币种词
                                           'REFERENCE', 'GLOBAL', 'TO', 'STRATEGIC', 'RATE',
                                           'CURRENCY', 'AMID', 'AFTER', 'BEFORE', 'OVER',
                                           'INTO', 'THROUGH', 'BETWEEN', 'UNDER', 'ABOVE',
                                           # 新增常见假阳性词
                                           'CNY', 'VOLATILITY', 'ADJUSTS', 'EAST', 'DOLLAR',
                                           'TENSIONS', 'ON', 'OIL', 'SURGE', 'PRICES', 'CANADIAN',
                                           'ESCALATING', 'SOARS', 'MIDDLE', 'WHALE', 'SIGNALS',
                                           'MILLION', 'SHIFT', 'PURCHASE', 'MAJOR', 'AT', 'LNG',
                                           'FORCE', 'QATAR', 'MAJEURE', 'CURBED', 'LAFFAN', 'RAS',
                                           'EXPORTS', 'ASSETS', 'BUY', 'DEFINES', 'TODAY', 'CRYPTO',
                                           'SINCE', 'UNTIL', 'AGAINST', 'DURING', 'WITHOUT',
                                           'WITHIN', 'ALONG', 'AMONG', 'BELOW',
                                           # 更多假阳性
                                           'FEES', 'ZERO', 'BEST', 'CALLS', 'RECENT', 'TRUTH',
                                           'CORRECTION', 'HEALTHY', 'RALLY', 'CRASH', 'PUMP',
                                           'DUMP', 'HIGH', 'LOW', 'GAIN', 'LOSS', 'RISE',
                                           'FALL', 'DROP', 'JUMP', 'SLIDE', 'DIP', 'TOP',
                                       # 更多假阳性
                                       'FINANCIAL', 'TOOL', 'VISA', 'LAUNCHES', 'AUTONOMOUS',
                                       'SOURCE', 'GET', 'MAKES', 'SAYS', 'WANTS', 'HELPS',
                                       'SHOWS', 'OFFERS', 'MEANS', 'NEEDS', 'LOOKS',
                                       'BOOST', 'PAYMENTS', 'DRIVEN', 'REVEALS', 'CRUCIAL'}

                            for symbol in set(symbols_found) - exclude_words:
                                coins.append({
                                    'symbol': symbol,
                                    'title': title,
                                    'source': 'coinmarketcap'
                                })

                        return coins
        except Exception as e:
            logger.warning(f"获取CoinMarketCap新闻失败: {e}")
        return []

    async def fetch_panews_flash(self) -> List[dict]:
        """获取PANews快讯"""
        try:
            async with aiohttp.ClientSession() as session:
                # PANews快讯页面
                url = "https://www.panewslab.com/zh/newsflash"
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                    'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
                    'Accept-Encoding': 'gzip, deflate'
                }
                proxy = "http://127.0.0.1:18080"
                async with session.get(url, headers=headers,
                                       timeout=aiohttp.ClientTimeout(total=15),
                                       proxy=proxy) as resp:
                    if resp.status == 200:
                        content = await resp.text()
                        coins = []

                        # 提取快讯内容
                        # PANews页面是动态渲染的，尝试提取可见的文本
                        texts = re.findall(r'>([^<]{20,200})<', content)

                        for text in texts[:50]:
                            # 从文本提取币种符号
                            text_upper = text.upper()

                            # 检查已知币种名称
                            symbol_mentions = []
                            text_lower = text.lower()
                            for key, symbol in self.known_symbols.items():
                                if key in text_lower:
                                    symbol_mentions.append(symbol)

                            # 提取大写字母组合
                            caps = re.findall(r'\b([A-Z]{2,10})\b', text_upper)
                            symbol_mentions.extend(caps)

                            # 过滤
                            exclude_words = {'THE', 'AND', 'FOR', 'NEW', 'FROM', 'WITH',
                                           'THIS', 'THAT', 'NEWS', 'WILL', 'ARE', 'HAS',
                                           'BUT', 'NOT', 'YOU', 'ALL', 'CAN', 'PANEWS',
                                           'WEB', 'APP', 'GMT', 'UTC', 'CEO', 'SEC',
                                           'UK', 'US', 'EU', 'FED', 'ETF', 'NFT',
                                           'MARKETS', 'OPINION', 'IPO', 'DAO', 'PROTOCOL',
                                           'PLATFORM', 'EXCHANGE', 'WALLET', 'TOKEN', 'COIN',
                                           'TRADING', 'MARKET', 'PRICE', 'CHAIN', 'NETWORK',
                                           # 新增常见假阳性词
                                           'CNY', 'VOLATILITY', 'ADJUSTS', 'EAST', 'DOLLAR',
                                           'TENSIONS', 'ON', 'OIL', 'SURGE', 'PRICES', 'CANADIAN',
                                           'ESCALATING', 'SOARS', 'MIDDLE', 'WHALE', 'SIGNALS',
                                           'MILLION', 'SHIFT', 'PURCHASE', 'MAJOR', 'AT', 'LNG',
                                           'FORCE', 'QATAR', 'MAJEURE', 'CURBED', 'LAFFAN', 'RAS',
                                           'EXPORTS', 'ASSETS', 'BUY', 'DEFINES', 'TODAY', 'CRYPTO',
                                           'AMID', 'OVER', 'AFTER', 'BEFORE', 'SINCE', 'UNTIL',
                                           'AGAINST', 'BETWEEN', 'THROUGH', 'DURING', 'WITHOUT',
                                           'WITHIN', 'ALONG', 'AMONG', 'ABOVE', 'BELOW',
                                           # 更多假阳性
                                           'FEES', 'ZERO', 'BEST', 'CALLS', 'RECENT', 'TRUTH',
                                           'CORRECTION', 'HEALTHY', 'RALLY', 'CRASH', 'PUMP',
                                           'DUMP', 'HIGH', 'LOW', 'GAIN', 'LOSS', 'RISE',
                                           'FALL', 'DROP', 'JUMP', 'SLIDE', 'DIP', 'TOP',
                                       # 更多假阳性
                                       'FINANCIAL', 'TOOL', 'VISA', 'LAUNCHES', 'AUTONOMOUS',
                                       'SOURCE', 'GET', 'MAKES', 'SAYS', 'WANTS', 'HELPS',
                                       'SHOWS', 'OFFERS', 'MEANS', 'NEEDS', 'LOOKS',
                                       'BOOST', 'PAYMENTS', 'DRIVEN', 'REVEALS', 'CRUCIAL'}

                            for symbol in set(symbol_mentions) - exclude_words:
                                coins.append({
                                    'symbol': symbol,
                                    'content': text[:100],
                                    'source': 'panews'
                                })

                        return coins
        except Exception as e:
            logger.warning(f"获取PANews快讯失败: {e}")
        return []

    async def fetch_altcoin_daily_news(self) -> List[dict]:
        """获取Altcoin Daily新闻 (通过RSS/YouTube)"""
        try:
            async with aiohttp.ClientSession() as session:
                # Altcoin Daily YouTube RSS feed
                url = "https://www.youtube.com/feeds/videos.xml?channel_id=UCGyqECE5dP6UiU5n5nDvceg"
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                }
                proxy = "http://127.0.0.1:18080"
                async with session.get(url, headers=headers,
                                       timeout=aiohttp.ClientTimeout(total=15),
                                       proxy=proxy) as resp:
                    if resp.status == 200:
                        content = await resp.text()
                        coins = []
                        root = ET.fromstring(content)

                        # 使用Atom命名空间
                        ns = {'atom': 'http://www.w3.org/2005/Atom',
                              'media': 'http://search.yahoo.com/mrss/'}

                        entries = root.findall('.//atom:entry', ns)[:20]

                        for entry in entries:
                            title_elem = entry.find('atom:title', ns)
                            if title_elem is not None and title_elem.text:
                                title = title_elem.text.upper()

                                # 从标题提取币种
                                symbols_found = set()

                                # 特殊处理常见币种名称
                                if 'BITCOIN' in title or 'BTC' in title:
                                    symbols_found.add('BTC')
                                if 'ETHEREUM' in title or 'ETH' in title:
                                    symbols_found.add('ETH')
                                if 'SOLANA' in title or 'SOL' in title:
                                    symbols_found.add('SOL')
                                if 'XRP' in title or 'RIPPLE' in title:
                                    symbols_found.add('XRP')
                                if 'DOGE' in title or 'DOGECOIN' in title:
                                    symbols_found.add('DOGE')
                                if 'CARDANO' in title or 'ADA' in title:
                                    symbols_found.add('ADA')

                                # 提取大写字母组合
                                caps = re.findall(r'\b([A-Z]{2,10})\b', title)
                                symbols_found.update(caps)

                                # 过滤
                                exclude_words = {'THE', 'AND', 'FOR', 'NEW', 'FROM', 'WITH',
                                               'THIS', 'THAT', 'NEWS', 'WILL', 'ARE', 'HAS',
                                               'BUT', 'NOT', 'YOU', 'ALL', 'CAN', 'ALTCOIN',
                                               'DAILY', 'CRYPTO', 'BREAKING', 'HUGE', 'BUY',
                                               'PRICE', 'MARKET', 'WHY', 'HOW', 'WHAT', 'NOW',
                                               # 新增常见假阳性词
                                               'CNY', 'VOLATILITY', 'ADJUSTS', 'EAST', 'DOLLAR',
                                               'TENSIONS', 'ON', 'OIL', 'SURGE', 'PRICES', 'CANADIAN',
                                               'ESCALATING', 'SOARS', 'MIDDLE', 'WHALE', 'SIGNALS',
                                               'MILLION', 'SHIFT', 'PURCHASE', 'MAJOR', 'AT', 'LNG',
                                               'FORCE', 'QATAR', 'MAJEURE', 'CURBED', 'LAFFAN', 'RAS',
                                               'EXPORTS', 'ASSETS', 'DEFINES', 'TODAY',
                                               'AMID', 'OVER', 'AFTER', 'BEFORE', 'SINCE', 'UNTIL',
                                               'AGAINST', 'BETWEEN', 'THROUGH', 'DURING', 'WITHOUT',
                                               'WITHIN', 'ALONG', 'AMONG', 'ABOVE', 'BELOW',
                                           # 更多假阳性
                                           'FEES', 'ZERO', 'BEST', 'CALLS', 'RECENT', 'TRUTH',
                                           'CORRECTION', 'HEALTHY', 'RALLY', 'CRASH', 'PUMP',
                                           'DUMP', 'HIGH', 'LOW', 'GAIN', 'LOSS', 'RISE',
                                           'FALL', 'DROP', 'JUMP', 'SLIDE', 'DIP', 'TOP',
                                       # 更多假阳性
                                       'FINANCIAL', 'TOOL', 'VISA', 'LAUNCHES', 'AUTONOMOUS',
                                       'SOURCE', 'GET', 'MAKES', 'SAYS', 'WANTS', 'HELPS',
                                       'SHOWS', 'OFFERS', 'MEANS', 'NEEDS', 'LOOKS',
                                       'BOOST', 'PAYMENTS', 'DRIVEN', 'REVEALS', 'CRUCIAL'}

                                for symbol in symbols_found - exclude_words:
                                    coins.append({
                                        'symbol': symbol,
                                        'title': title_elem.text,
                                        'source': 'altcoin_daily'
                                    })

                        return coins
        except Exception as e:
            logger.warning(f"获取Altcoin Daily新闻失败: {e}")
        return []

    async def fetch_crypto_news_aggregated(self) -> List[dict]:
        """聚合多个新闻源"""
        all_coins = []

        # 并发获取所有新闻源
        tasks = [
            self.fetch_cointelegraph_news(),
            self.fetch_coinmarketcap_news(),
            self.fetch_panews_flash(),
            self.fetch_altcoin_daily_news(),
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        for result in results:
            if isinstance(result, list) and len(result) > 0:
                all_coins.extend(result)

        logger.info(f"从新闻源收集到 {len(all_coins)} 个提及")
        return all_coins

    def normalize_symbol(self, symbol: str) -> Optional[str]:
        """标准化币种符号"""
        symbol = symbol.lower().strip()
        # 移除常见后缀
        for suffix in ['-usdt', 'usdt', '-usd', 'usd', '/usdt', '/usd']:
            symbol = symbol.replace(suffix, '')

        # 查找映射
        if symbol in self.known_symbols:
            return self.known_symbols[symbol]

        # 如果是有效的币种符号格式
        if len(symbol) >= 2 and len(symbol) <= 10 and symbol.isalpha():
            return symbol.upper()

        return None

    async def check_exchange_support(self, symbol: str, exchange) -> bool:
        """检查交易所是否支持该交易对"""
        try:
            # 构建可能的交易对格式
            possible_pairs = [
                f"{symbol}/USDT:USDT",  # 合约
                f"{symbol}/USDT",        # 现货
            ]

            # 获取交易所支持的所有交易对
            if hasattr(exchange, 'markets') and exchange.markets:
                for pair in possible_pairs:
                    if pair in exchange.markets:
                        return True

            # 如果没有缓存的市场数据，尝试查询
            # 注意：这里需要传入实际的exchange对象
            return False
        except Exception as e:
            logger.warning(f"检查交易所支持失败: {e}")
            return False

    async def discover_new_pairs(self, exchange=None) -> Dict[str, dict]:
        """发现新的热门交易对"""
        now = datetime.now()

        # 检查更新间隔
        if self.last_update and (now - self.last_update).total_seconds() < self.update_interval:
            return self.discovered_pairs

        logger.info("🔍 开始发现新交易对...")

        all_coins = []

        # 并发获取多个数据源
        tasks = [
            self.fetch_coingecko_trending(),
            self.fetch_coingecko_top_gainers(),
            self.fetch_dexscreener_trending(),
            self.fetch_binance_new_listings(),
            self.fetch_twitter_trending(),
            # 新增新闻源
            self.fetch_cointelegraph_news(),
            self.fetch_coinmarketcap_news(),
            self.fetch_panews_flash(),
            self.fetch_altcoin_daily_news(),
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        for result in results:
            if isinstance(result, list) and len(result) > 0:
                all_coins.extend(result)

        # 如果所有API都失败，使用备用数据
        if not all_coins:
            logger.warning("所有API调用失败，使用备用热门列表")
            fallback = await self.fetch_fallback_trending()
            all_coins.extend(fallback)

        logger.info(f"收集到 {len(all_coins)} 个潜在热门币种")

        # 处理发现的币种
        new_discoveries = {}
        for coin in all_coins:
            symbol = self.normalize_symbol(coin.get('symbol', ''))
            if not symbol:
                continue

            # 计算热门得分
            score = self._calculate_trending_score(coin)

            if score > 0.3:  # 只保留得分较高的
                pair = f"{symbol}/USDT:USDT"

                # 检查交易所支持
                exchange_supported = exchange and await self.check_exchange_support(symbol, exchange)

                new_discoveries[symbol] = {
                    'symbol': symbol,
                    'pair': pair,
                    'score': score,
                    'source': coin.get('source', 'unknown'),
                    'discovered_at': now.isoformat(),
                    'exchange_supported': exchange_supported,
                    'details': coin
                }

        # 更新缓存
        self.discovered_pairs = new_discoveries
        self.last_update = now
        self.save_cache()

        logger.info(f"✅ 发现 {len(new_discoveries)} 个热门交易对")

        return new_discoveries

    def _calculate_trending_score(self, coin: dict) -> float:
        """计算热门得分"""
        score = 0.0
        source = coin.get('source', '')

        # 根据数据源加权
        if source == 'coingecko_trending':
            rank = coin.get('market_cap_rank', 100)
            score += max(0, (100 - rank) / 100)  # 排名越前得分越高
            score += min(1.0, coin.get('score', 0) / 10)

        elif source == 'coingecko_gainers':
            change = coin.get('price_change_24h', 0)
            score += min(1.0, change / 50)  # 涨幅越高得分越高
            rank = coin.get('market_cap_rank', 100)
            score += max(0, (100 - rank) / 200)

        elif source == 'dexscreener':
            score += 0.7  # DexScreener上的项目默认给予较高关注

        elif source == 'binance_new_listing':
            score += 1.0  # 新上线币种给予最高关注

        elif source == 'twitter_trending':
            mentions = coin.get('mentions', 0)
            sentiment = coin.get('sentiment', 0.5)
            score += min(0.5, mentions / 5000) * sentiment

        # 新闻来源评分
        elif source == 'cointelegraph':
            score += 0.6  # Cointelegraph是权威加密媒体

        elif source == 'coinmarketcap':
            score += 0.55  # CMC头条新闻

        elif source == 'panews':
            score += 0.5  # PANews快讯

        elif source == 'altcoin_daily':
            score += 0.65  # Altcoin Daily YouTube频道，影响力较大

        return min(1.0, score)

    def get_top_pairs(self, limit: int = 10) -> List[dict]:
        """获取热门交易对列表"""
        sorted_pairs = sorted(
            self.discovered_pairs.values(),
            key=lambda x: x.get('score', 0),
            reverse=True
        )
        return sorted_pairs[:limit]

    def get_tradable_pairs(self, current_pairs: List[str], limit: int = 5) -> List[str]:
        """获取可交易的新交易对 (不在当前列表中的)"""
        current_symbols = set()
        for pair in current_pairs:
            # 提取币种符号
            symbol = pair.split('/')[0].replace(':USDT', '')
            current_symbols.add(symbol)

        new_pairs = []
        for symbol, data in sorted(self.discovered_pairs.items(),
                                   key=lambda x: x[1].get('score', 0),
                                   reverse=True):
            if symbol not in current_symbols and data.get('exchange_supported', True):
                new_pairs.append(data.get('pair', f"{symbol}/USDT:USDT"))
                if len(new_pairs) >= limit:
                    break

        return new_pairs


# 单例实例
_discovery_instance = None

def get_discovery() -> DynamicPairDiscovery:
    """获取单例实例"""
    global _discovery_instance
    if _discovery_instance is None:
        _discovery_instance = DynamicPairDiscovery()
    return _discovery_instance


async def discover_and_get_pairs(exchange=None, current_pairs: List[str] = None) -> List[str]:
    """发现并返回新的可交易对"""
    discovery = get_discovery()
    await discovery.discover_new_pairs(exchange)

    if current_pairs is None:
        current_pairs = []

    return discovery.get_tradable_pairs(current_pairs)


if __name__ == "__main__":
    # 测试
    async def test():
        discovery = DynamicPairDiscovery()
        pairs = await discovery.discover_new_pairs()

        print("\n" + "="*60)
        print("🔥 发现的热门交易对:")
        print("="*60)

        for i, (symbol, data) in enumerate(sorted(pairs.items(),
                                                   key=lambda x: x[1].get('score', 0),
                                                   reverse=True)[:15], 1):
            score = data.get('score', 0)
            source = data.get('source', '')
            print(f"{i:2}. {symbol:8} | 得分: {score:.2f} | 来源: {source}")

    asyncio.run(test())