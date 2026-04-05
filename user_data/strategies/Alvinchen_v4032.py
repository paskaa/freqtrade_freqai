"""
ADX/DI Strategy - v4032 (ATR动态止盈+链上数据版)
==========================================

基于v4030(79.37%利润)优化：
- v4032核心改动:
  1. ATR动态止盈: 高波动收紧阈值(快获利)、低波动放宽(耐心等待)
     - 高波动(>3.5%): threshold * 0.85 (收紧15%)
     - 低波动(<2%): threshold * 1.2 (放宽20%)
  2. 链上数据过滤: 资金费率/多空比极端时拒绝入场(生产环境实时生效)
  3. 多时间框架: 1h EMA趋势已在base条件中使用(经测试MACD过滤无效)

回测结果 (2025-04-01 ~ 2026-03-28):
- 403笔交易, 79.82%利润, 66.5%胜率, 11.05%回撤
- 对比v4030: 利润+0.45%, 回撤-1.84%

注意: 多时间框架MACD过滤经测试无效果，已移除
"""

import logging
import numpy as np
import pandas as pd
from pandas import DataFrame
from typing import Optional, Dict, Any, Union
from collections import OrderedDict
from datetime import datetime, timedelta
import sys
import os

STRATEGY_DIR = os.path.dirname(os.path.abspath(__file__))
if STRATEGY_DIR not in sys.path:
    sys.path.insert(0, STRATEGY_DIR)

from freqtrade.strategy import IStrategy, DecimalParameter, IntParameter, informative
from freqtrade.persistence import Trade
from freqtrade.enums import RunMode
import talib.abstract as ta
import freqtrade.vendor.qtpylib.indicators as qtpylib
from functools import reduce

try:
    from free_sentiment_api import (
        get_sentiment_for_trading,
        fetch_fear_greed_index,
        fetch_reddit_sentiment,
        fetch_elfa_token_news
    )
    FREE_SENTIMENT_AVAILABLE = True
except ImportError:
    FREE_SENTIMENT_AVAILABLE = False

try:
    from free_onchain_data import (
        get_funding_rate,
        get_long_short_ratio,
        get_market_sentiment
    )
    FREE_ONCHAIN_AVAILABLE = True
except ImportError:
    FREE_ONCHAIN_AVAILABLE = False

try:
    from orderbook_analyzer import (
        analyze_orderbook,
        get_obi,
        OrderBookAnalyzer
    )
    ORDERBOOK_AVAILABLE = True
except ImportError:
    ORDERBOOK_AVAILABLE = False

logger = logging.getLogger(__name__)


class Alvinchen_v4032(IStrategy):
    """
    v4032 - 多时间框架+ATR动态出场+链上数据版

    优化点：
    1. 多时间框架确认 (1h EMA趋势过滤)
    2. ATR动态止盈止损
    3. 波动率自适应参数
    4. 链上数据入场过滤
    """

    INTERFACE_VERSION = 3
    can_short = True
    use_exit_signal = True
    exit_profit_only = False
    exit_profit_offset = 0.0

    timeframe = '15m'
    startup_candle_count = 1000

    # 画图配置 - 用于分析入场出场点
    plot_config = {
        'main_plot': {
            'ema_20': {'color': 'red'},
            'ema_50': {'color': 'blue'},
            'ema_200': {'color': 'gray'},
        },
        'subplots': {
            'RSI': {
                'rsi': {'color': 'purple'},
            },
            'ADX': {
                'adx': {'color': 'orange'},
                'di_diff': {'color': 'green'},
            },
            'PricePos': {
                'price_position': {'color': 'blue'},
                'daily_price_position': {'color': 'red'},
            },
            'MACD': {
                'macdhist': {'type': 'bar'},
            }
        }
    }

    def informative_pairs(self):
        whitelist = self.config.get('exchange', {}).get('pair_whitelist', [])
        pairs = [(pair, '1h') for pair in whitelist]
        pairs.append(('BTC/USDT:USDT', '1d'))
        return pairs

    # hyperopt优化参数 (2026-03-31)
    buy_rsi_long_lower = DecimalParameter(45, 65, default=55.4, decimals=1, optimize=True, space='buy')
    buy_rsi_long_upper = DecimalParameter(65, 80, default=77.6, decimals=1, optimize=True, space='buy')
    buy_rsi_short_upper = DecimalParameter(25, 45, default=31.4, decimals=1, optimize=True, space='buy')
    buy_rsi_short_lower = DecimalParameter(15, 30, default=19.9, decimals=1, optimize=True, space='buy')

    # v4016: 放宽ADX阈值增加信号，然后用价格位置过滤
    buy_adx_tier1 = DecimalParameter(25, 25, default=25.0, decimals=1, optimize=False, space='buy')
    buy_adx_tier2 = DecimalParameter(28, 28, default=28.0, decimals=1, optimize=False, space='buy')
    buy_adx_tier3 = DecimalParameter(32, 32, default=32.0, decimals=1, optimize=False, space='buy')
    buy_adx_tier4 = DecimalParameter(36, 36, default=36.0, decimals=1, optimize=False, space='buy')

    buy_di_tier1 = DecimalParameter(2, 8, default=5.4, decimals=1, optimize=True, space='buy')
    buy_di_tier2 = DecimalParameter(4, 12, default=8.8, decimals=1, optimize=True, space='buy')
    buy_di_tier3 = DecimalParameter(4, 12, default=9.1, decimals=1, optimize=True, space='buy')
    buy_di_tier4 = DecimalParameter(7, 18, default=11.4, decimals=1, optimize=True, space='buy')

    buy_vol_tier1 = DecimalParameter(0.8, 1.5, default=1.18, decimals=2, optimize=True, space='buy')
    buy_vol_tier2 = DecimalParameter(0.9, 2.0, default=1.89, decimals=2, optimize=True, space='buy')
    buy_vol_tier3 = DecimalParameter(1.0, 2.5, default=1.08, decimals=2, optimize=True, space='buy')
    buy_vol_tier4 = DecimalParameter(1.0, 2.5, default=2.44, decimals=2, optimize=True, space='buy')

    sell_rsi_overbought = DecimalParameter(70, 85, default=82.9, decimals=1, optimize=True, space='sell')
    sell_rsi_oversold = DecimalParameter(20, 35, default=29.7, decimals=1, optimize=True, space='sell')
    sell_adx_weak_threshold = DecimalParameter(15, 25, default=20.6, decimals=1, optimize=True, space='sell')
    sell_max_holding_hours = IntParameter(48, 120, default=74, optimize=True, space='sell')
    sell_max_holding_profit_extend = DecimalParameter(0.03, 0.10, default=0.07, decimals=2, optimize=True, space='sell')
    sell_profit_lock_threshold = DecimalParameter(0.03, 0.08, default=0.043, decimals=3, optimize=True, space='sell')
    sell_profit_lock_ratio = DecimalParameter(0.5, 0.9, default=0.625, decimals=3, optimize=True, space='sell')

    adx_threshold = 19.788
    volume_mult = 1.221

    # v4014: 收紧止损阈值
    tier1_initial_stoploss = 0.18   # Tier1: 18%
    tier1_profit_stoploss = 0.05
    tier2_initial_stoploss = 0.15   # Tier2: 15%
    tier2_profit_stoploss = 0.04
    tier3_initial_stoploss = 0.12   # Tier3: 12%
    tier3_profit_stoploss = 0.03
    tier4_initial_stoploss = 0.10   # Tier4: 10%
    tier4_profit_stoploss = 0.02

    # 4层币种分级
    tier1_coins = ['BTC', 'ETH']
    tier2_coins = [
        'BNB', 'SOL', 'XRP', 'ADA', 'DOGE', 'AVAX',
        'LINK', 'DOT', 'LTC', 'ATOM', 'BCH', 'ARB',
        'OP', 'FIL', 'APT', 'NEAR', 'INJ', 'AAVE',
        'CRV', 'HYPE', 'SIREN', 'ONT', 'JTO', 'BR',
        'RENDER', 'PAXG', 'SIGN', 'DYDX', 'ONDO',
        'ATH', 'PENGU', 'GALA', 'TRX', 'XLM',
        'XMR', 'ICP', 'VET', 'XTZ', 'ZEC', 'SUI',
        'ALGO', 'XAUT', 'KAS', 'HBAR', 'MNT',
        'FTM', 'AXS', 'SAND', 'MANA', 'UNI', 'MKR',
        'COMP', 'SNX', 'LDO', 'IMX', 'BAT', 'ETC',
        'DASH', 'JUP', 'GRASS', 'PENDLE', 'DUSK',
        'ORDI', 'PIXEL', 'POPCAT'
    ]
    tier3_coins = [
        'BARD', 'EIGEN', 'SEI', 'POL', 'ETHFI',
        'AERO', 'JST', 'WOO', 'BLUR', 'AGIX',
        'RDNT', 'ARK', 'STX', 'C98', 'MASK',
        'WLD', 'PEOPLE', 'GDTC'
    ]
    tier4_coins = [
        'KAITO', 'BRETT', 'MEW', 'TON', 'NOT',
        'CATI', 'H', 'BOME', 'SLERF', 'FWOG',
        'MOG', 'AIXBT', 'VIRTUAL', 'AI16Z', 'ZEREBRO',
        'GUN', 'PIPPIN', 'FARTCOIN', 'MEMEFI', 'LUCE'
    ]

    tier1_adx = 22
    tier1_di = 4
    tier1_vol = 1.0

    tier2_adx = 25
    tier2_di = 5
    tier2_vol = 1.05

    tier3_adx = 30
    tier3_di = 7
    tier3_vol = 1.1

    tier4_adx = 35
    tier4_di = 9
    tier4_vol = 1.2

    regime_stability_candles = 3

    enable_sentiment_check = True
    enable_onchain_filter = True
    enable_news_filter = True
    enable_orderbook_analysis = True
    sentiment_bullish_threshold = 0.65
    sentiment_bearish_threshold = 0.35
    sentiment_extreme_fear = 25
    sentiment_extreme_greed = 75
    strict_funding_filter = False
    strict_lsr_filter = False
    sentiment_cache_ttl = 300
    news_negative_threshold = 0.7
    sentiment_allow_contrarian_shorts = True
    sentiment_contrarian_adx_threshold = 30.0
    balance_check_threshold = 0.75
    news_check_cooldown = 3600

    obi_threshold = 0.3
    obi_strong_threshold = 0.5
    spread_threshold = 0.1
    large_order_mult = 3.0
    orderbook_cache_ttl = 5

    max_leverage = 1
    min_leverage = 1
    leverage_enabled = False

    leverage_threshold_medium = 0.70
    leverage_threshold_high = 0.80
    leverage_threshold_very_high = 0.90
    leverage_threshold_extreme = 0.95

    stoploss = -0.15
    use_custom_stoploss = True

    trailing_stop = False
    trailing_stop_positive = 0.0
    trailing_stop_positive_offset = 0.0
    trailing_only_offset_is_reached = False

    profit_lock_threshold = 0.052
    profit_lock_ratio = 0.761

    position_adjustment_enable = False
    max_entry_position_adjustment = -1
    add_position_threshold = -0.05
    add_position_ratio = 0.5

    minimal_roi = {}

    tier1_profit_targets = [0.05, 0.08, 0.12]
    tier2_profit_targets = [0.04, 0.06, 0.10]
    tier3_profit_targets = [0.03, 0.05, 0.08]
    tier4_profit_targets = [0.02, 0.04, 0.06]

    _backtest_mode = False
    _dry_run_mode = False

    def __init__(self, config: dict) -> None:
        super().__init__(config)
        self.freqai_enabled = config.get('freqai', {}).get('enabled', False)
        self._dry_run_mode = config.get('dry_run', False)

        logger.info(f"v4014 Production Strategy - enabled: {self.freqai_enabled}")

        self._sentiment_cache = {}
        self._onchain_cache = {}
        self._news_cache = {}
        self._last_news_check = {}
        self._orderbook_cache = {}
        self._leverage_cache = {}
        self._profit_tier_cache = {}
        self._last_market_regime = {}

    def _hma(self, series: pd.Series, period: int) -> pd.Series:
        half_period = int(period / 2)
        sqrt_period = int(np.sqrt(period))
        wma_half = ta.WMA(series, timeperiod=half_period)
        wma_full = ta.WMA(series, timeperiod=period)
        raw_hma = 2 * wma_half - wma_full
        hma = ta.WMA(raw_hma, timeperiod=sqrt_period)
        return hma

    @informative('1h')
    def populate_indicators_1h(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # 使用不与主dataframe重复的列名，避免Freqtrade合并时跳过
        dataframe['ema_20'] = ta.EMA(dataframe['close'], timeperiod=20)
        dataframe['ema_50'] = ta.EMA(dataframe['close'], timeperiod=50)
        dataframe['ema_200'] = ta.EMA(dataframe['close'], timeperiod=200)
        dataframe['adx'] = ta.ADX(dataframe, timeperiod=14)
        # v4032修复: 使用不同列名避免与主dataframe冲突
        try:
            macd, macdsignal, macdhist = ta.MACD(dataframe['close'], fastperiod=12, slowperiod=26, signalperiod=9)
            dataframe['macd_hourly'] = macd
            dataframe['macdsignal_hourly'] = macdsignal
            dataframe['macdhist_hourly'] = macdhist
        except Exception as e:
            logger.error(f"MACD计算失败: {e}")
        try:
            dataframe['rsi_hourly'] = ta.RSI(dataframe['close'], timeperiod=14)
        except Exception as e:
            logger.error(f"RSI计算失败: {e}")
        return dataframe

    @informative('1d', 'BTC/USDT:USDT')
    def populate_indicators_1d_btc(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe['ema_50'] = ta.EMA(dataframe['close'], timeperiod=50)
        dataframe['ema_200'] = ta.EMA(dataframe['close'], timeperiod=200)
        return dataframe

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe['rsi'] = ta.RSI(dataframe['close'], timeperiod=14)
        dataframe['rsi_fast'] = ta.RSI(dataframe['close'], timeperiod=7)
        dataframe['rsi_2'] = ta.RSI(dataframe['close'], timeperiod=2)

        dataframe['roc'] = ta.ROC(dataframe['close'], timeperiod=10)
        dataframe['roc_2'] = ta.ROC(dataframe['close'], timeperiod=2)

        macd, macdsignal, macdhist = ta.MACD(dataframe['close'])
        dataframe['macd'] = macd
        dataframe['macdsignal'] = macdsignal
        dataframe['macdhist'] = macdhist

        bb = qtpylib.bollinger_bands(dataframe['close'], window=20, stds=2)
        dataframe['bb_lower'] = bb['lower']
        dataframe['bb_upper'] = bb['upper']
        dataframe['bb_pct'] = (dataframe['close'] - bb['lower']) / (bb['upper'] - bb['lower'] + 1e-8)
        dataframe['bb_width'] = (bb['upper'] - bb['lower']) / (bb['mid'] + 1e-8)

        dataframe['ema_20'] = ta.EMA(dataframe['close'], timeperiod=20)
        dataframe['ema_50'] = ta.EMA(dataframe['close'], timeperiod=50)
        dataframe['ema_100'] = ta.EMA(dataframe['close'], timeperiod=100)
        dataframe['ema_200'] = ta.EMA(dataframe['close'], timeperiod=200)

        dataframe['wma_20'] = ta.WMA(dataframe['close'], timeperiod=20)
        dataframe['hma_20'] = self._hma(dataframe['close'], 20)

        dataframe['adx'] = ta.ADX(dataframe, timeperiod=14)
        dataframe['plus_di'] = ta.PLUS_DI(dataframe, timeperiod=14)
        dataframe['minus_di'] = ta.MINUS_DI(dataframe, timeperiod=14)
        dataframe['di_diff'] = dataframe['plus_di'] - dataframe['minus_di']

        dataframe['atr'] = ta.ATR(dataframe, timeperiod=14)
        dataframe['atr_pct'] = dataframe['atr'] / dataframe['close']

        dataframe['volume_mean_20'] = dataframe['volume'].rolling(20).mean()
        dataframe['volume_ratio'] = dataframe['volume'] / (dataframe['volume_mean_20'] + 1e-8)

        dataframe['mfi'] = ta.MFI(dataframe, timeperiod=14)

        dataframe['vwap_proxy'] = (
            (dataframe['close'] * dataframe['volume']).cumsum() /
            (dataframe['volume'].cumsum() + 1e-8)
        )

        dataframe['momentum_5'] = dataframe['close'] / dataframe['close'].shift(5) - 1
        dataframe['cci'] = ta.CCI(dataframe, timeperiod=20)

        dataframe['market_regime'] = np.where(
            dataframe['ema_50'] > dataframe['ema_200'], 1,
            np.where(dataframe['ema_50'] < dataframe['ema_200'], -1, 0)
        )

        adx_strong = dataframe['adx'] > 25
        ema_bullish = dataframe['ema_20'] > dataframe['ema_50']
        ema_bearish = dataframe['ema_20'] < dataframe['ema_50']

        dataframe['state_strong_uptrend'] = (adx_strong & ema_bullish).astype(int)
        dataframe['state_strong_downtrend'] = (adx_strong & ema_bearish).astype(int)
        dataframe['state_range_bound'] = (dataframe['adx'] < 20).astype(int)
        dataframe['state_adx_breakout'] = (
            (dataframe['adx'] > 25) & (dataframe['adx'].shift(5) < 20)
        ).astype(int)

        dataframe['momentum_score'] = np.clip(
            (dataframe['adx'] / 100) * 50 +
            (np.abs(dataframe['di_diff']) / 20) * 30 +
            (dataframe['roc'] / 10) * 20,
            0, 100
        )

        dataframe['rsi_mfi_oversold'] = (dataframe['rsi_2'] < 30) & (dataframe['mfi'] < 30)
        dataframe['rsi_mfi_overbought'] = (dataframe['rsi_2'] > 70) & (dataframe['mfi'] > 70)
        dataframe['above_vwap'] = dataframe['close'] > dataframe['vwap_proxy']
        dataframe['hma_above_ema'] = dataframe['hma_20'] > dataframe['ema_20']

        window = 50
        dataframe['fib_low'] = dataframe['low'].rolling(window=window).min()
        dataframe['fib_high'] = dataframe['high'].rolling(window=window).max()
        diff = dataframe['fib_high'] - dataframe['fib_low']
        diff = diff.replace(0, np.nan)
        dataframe['fib_382'] = dataframe['fib_low'] + diff * 0.382
        dataframe['fib_618'] = dataframe['fib_low'] + diff * 0.618
        dataframe['fib_786'] = dataframe['fib_low'] + diff * 0.786
        tolerance = diff * 0.02
        dataframe['at_fib_618'] = np.abs(dataframe['close'] - dataframe['fib_618']) < tolerance
        dataframe['at_fib_382'] = np.abs(dataframe['close'] - dataframe['fib_382']) < tolerance
        dataframe['in_fib_range'] = (dataframe['close'] >= dataframe['fib_low']) & (dataframe['close'] <= dataframe['fib_high'])

        # v4016: 价格位置指标 - 避免追高杀跌
        # 近期高低点（20根K线 = 5小时）
        dataframe['recent_high_20'] = dataframe['high'].rolling(window=20).max()
        dataframe['recent_low_20'] = dataframe['low'].rolling(window=20).min()
        dataframe['recent_range_20'] = dataframe['recent_high_20'] - dataframe['recent_low_20']

        # 价格位置百分比 (0=最低, 100=最高)
        dataframe['price_position'] = (
            (dataframe['close'] - dataframe['recent_low_20']) /
            (dataframe['recent_range_20'] + 1e-8) * 100
        )

        # 价格偏离EMA百分比
        dataframe['price_deviation_ema20'] = (dataframe['close'] - dataframe['ema_20']) / dataframe['ema_20'] * 100
        dataframe['price_deviation_ema50'] = (dataframe['close'] - dataframe['ema_50']) / dataframe['ema_50'] * 100

        # 判断是否在局部高点/低点附近
        dataframe['near_local_high'] = dataframe['price_position'] > 80  # 在近期高点附近
        dataframe['near_local_low'] = dataframe['price_position'] < 20   # 在近期低点附近

        # v4030: 日线级别价格位置过滤 - 优化版
        # 使用100根K线(25小时)捕捉日级别高低点
        dataframe['daily_high_100'] = dataframe['high'].rolling(window=100).max()
        dataframe['daily_low_100'] = dataframe['low'].rolling(window=100).min()
        dataframe['daily_range_100'] = dataframe['daily_high_100'] - dataframe['daily_low_100']
        dataframe['daily_price_position'] = (
            (dataframe['close'] - dataframe['daily_low_100']) /
            (dataframe['daily_range_100'] + 1e-8) * 100
        )
        # 日线级别高低点判断
        dataframe['near_daily_low'] = dataframe['daily_price_position'] < 20  # 在日线低位
        dataframe['near_daily_high'] = dataframe['daily_price_position'] > 80  # 在日线高位

        if self.freqai_enabled:
            dataframe = self.freqai.start(dataframe, metadata, self)
        else:
            dataframe = self.set_freqai_targets(dataframe, metadata)

        return dataframe

    def set_freqai_targets(self, dataframe: DataFrame, metadata: dict, **kwargs) -> DataFrame:
        label_period = self.config.get('freqai', {}).get('feature_parameters', {}) \
            .get('label_period_candles', 12)
        dataframe["&-s_close_mean"] = (
            dataframe["close"]
            .shift(-label_period)
            .rolling(label_period)
            .mean()
            / dataframe["close"]
            - 1
        )
        return dataframe

    def _get_pair_tier(self, pair: str) -> int:
        coin_base = pair.split('/')[0] if '/' in pair else pair
        if coin_base in self.tier1_coins:
            return 1
        elif coin_base in self.tier2_coins:
            return 2
        elif coin_base in self.tier3_coins:
            return 3
        elif coin_base in self.tier4_coins:
            return 4
        return 4

    def _detect_market_regime(self, dataframe: DataFrame, pair: str = "BTC") -> str:
        """
        市场判断：使用BTC 1d EMA数据
        列名格式: btc_usdt_ema_50_1d, btc_usdt_ema_200_1d (Freqtrade informative decorator)
        """
        try:
            # BTC 1d EMA列名 - Freqtrade informative decorator实际命名格式
            possible_ema50_cols = ['btc_usdt_ema_50_1d', 'ema_50_1d_BTC_USDT_USDT']
            possible_ema200_cols = ['btc_usdt_ema_200_1d', 'ema_200_1d_BTC_USDT_USDT']

            # 尝试所有可能的列名格式
            ema50_col = None
            ema200_col = None
            for col in possible_ema50_cols:
                if col in dataframe.columns:
                    ema50_col = col
                    break
            for col in possible_ema200_cols:
                if col in dataframe.columns:
                    ema200_col = col
                    break

            # 优先使用BTC 1d数据
            if ema50_col and ema200_col:
                ema50 = dataframe[ema50_col].iloc[-1]
                ema200 = dataframe[ema200_col].iloc[-1]

                # 检查是否为有效数值
                if pd.notna(ema50) and pd.notna(ema200):
                    result = 'bullish' if ema50 > ema200 else 'bearish' if ema50 < ema200 else 'neutral'
                    return result

            # BTC 1d数据不存在，返回neutral
            return 'neutral'
        except Exception as e:
            logger.warning(f"Market regime detection failed: {e}")
            return 'neutral'

    def _get_adaptive_thresholds(self, pair: str, side: str, dataframe: DataFrame) -> tuple:
        tier = self._get_pair_tier(pair)
        market_regime = self._detect_market_regime(dataframe, pair)

        if tier == 1:
            adx_th = self.buy_adx_tier1.value
            di_th = self.buy_di_tier1.value
            vol_th = self.buy_vol_tier1.value
        elif tier == 2:
            adx_th = self.buy_adx_tier2.value
            di_th = self.buy_di_tier2.value
            vol_th = self.buy_vol_tier2.value
        elif tier == 3:
            adx_th = self.buy_adx_tier3.value
            di_th = self.buy_di_tier3.value
            vol_th = self.buy_vol_tier3.value
        else:
            adx_th = self.buy_adx_tier4.value
            di_th = self.buy_di_tier4.value
            vol_th = self.buy_vol_tier4.value

        if market_regime == 'bearish':
            if side == 'short':
                adx_th = max(15, adx_th * 0.75)
                di_th = max(3, di_th * 0.75)
                vol_th = max(0.95, vol_th * 0.95)
            else:
                adx_th = adx_th * 1.3
                di_th = di_th * 1.3
                vol_th = vol_th * 1.1
        elif market_regime == 'bullish':
            if side == 'long':
                adx_th = max(15, adx_th * 0.75)
                di_th = max(3, di_th * 0.75)
                vol_th = max(0.95, vol_th * 0.95)
            else:
                adx_th = adx_th * 1.3
                di_th = di_th * 1.3
                vol_th = vol_th * 1.1
        elif market_regime == 'neutral':
            pass

        return adx_th, di_th, vol_th

    def _calculate_signal_strength(self, dataframe: DataFrame, side: str) -> float:
        if dataframe is None or len(dataframe) < 1:
            return 50.0

        last_candle = dataframe.iloc[-1]

        adx = last_candle.get('adx', 0)
        if adx > 40:
            adx_score = 100
        elif adx > 30:
            adx_score = 75
        elif adx > 25:
            adx_score = 50
        elif adx > 20:
            adx_score = 25
        else:
            adx_score = 0

        di_diff = last_candle.get('di_diff', 0)
        if side == 'long':
            di_score = max(0, min(100, (di_diff / 15) * 100)) if di_diff > 0 else 0
        else:
            di_score = max(0, min(100, (-di_diff / 15) * 100)) if di_diff < 0 else 0

        ema_20 = last_candle.get('ema_20', 0)
        ema_50 = last_candle.get('ema_50', 0)
        if side == 'long':
            ema_score = 100 if ema_20 > ema_50 else 0
        else:
            ema_score = 100 if ema_20 < ema_50 else 0

        rsi = last_candle.get('rsi', 50)
        if 40 <= rsi <= 60:
            rsi_score = 100
        elif (rsi > 60 and rsi < 70) or (rsi < 40 and rsi > 30):
            rsi_score = 50
        else:
            rsi_score = 0

        vol_ratio = last_candle.get('volume_ratio', 1.0)
        if vol_ratio > 2.0:
            vol_score = 100
        elif vol_ratio > 1.5:
            vol_score = 75
        elif vol_ratio > 1.0:
            vol_score = 50
        else:
            vol_score = 25

        macdhist = last_candle.get('macdhist', 0)
        if side == 'long':
            macd_score = 100 if macdhist > 0 else 0
        else:
            macd_score = 100 if macdhist < 0 else 0

        total_score = (
            adx_score * 0.25 +
            di_score * 0.20 +
            ema_score * 0.15 +
            rsi_score * 0.15 +
            vol_score * 0.15 +
            macd_score * 0.10
        )

        return total_score

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        pair = metadata.get('pair', '')
        coin_base = pair.split('/')[0] if '/' in pair else pair

        market_regime = self._detect_market_regime(dataframe, pair)

        regime_stable = True
        if len(dataframe) >= self.regime_stability_candles:
            recent_closes = dataframe['close'].iloc[-self.regime_stability_candles:].tolist()
            if len(recent_closes) >= 3:
                direction = [1 if recent_closes[i] > recent_closes[i-1] else -1 if recent_closes[i] < recent_closes[i-1] else 0 for i in range(1, len(recent_closes))]
                if not (all(d == 1 for d in direction) or all(d == -1 for d in direction)):
                    regime_stable = False

        tier = self._get_pair_tier(pair)
        if tier == 1:
            tier_name = 'tier1'
        elif tier == 2:
            tier_name = 'tier2'
        elif tier == 3:
            tier_name = 'tier3'
        else:
            tier_name = 'tier4'

        long_adx_th, long_di_th, long_vol_th = self._get_adaptive_thresholds(pair, 'long', dataframe)
        short_adx_th, short_di_th, short_vol_th = self._get_adaptive_thresholds(pair, 'short', dataframe)

        has_1h_data = 'ema_200_1h' in dataframe.columns

        if has_1h_data:
            major_bullish = dataframe['ema_50_1h'] > dataframe['ema_200_1h']
            major_bearish = dataframe['ema_50_1h'] < dataframe['ema_200_1h']
        else:
            major_bullish = dataframe['ema_50'] > dataframe['ema_200']
            major_bearish = dataframe['ema_50'] < dataframe['ema_200']

        minor_bullish = dataframe['ema_20'] > dataframe['ema_50']
        minor_bearish = dataframe['ema_20'] < dataframe['ema_50']

        long_entry_base = (
            major_bullish &
            minor_bullish &
            (dataframe['adx'] > long_adx_th) &
            (dataframe['di_diff'] > long_di_th) &
            (dataframe['macdhist'] > 0) &
            (dataframe['rsi'] > self.buy_rsi_long_lower.value) &
            (dataframe['rsi'] < self.buy_rsi_long_upper.value) &
            (dataframe['volume_ratio'] > long_vol_th) &
            (dataframe['volume'] > 0)
        )

        short_entry_base = (
            major_bearish &
            minor_bearish &
            (dataframe['adx'] > short_adx_th) &
            (dataframe['di_diff'] < -short_di_th) &
            (dataframe['macdhist'] < 0) &
            (dataframe['rsi'] < self.buy_rsi_short_upper.value) &
            (dataframe['rsi'] > self.buy_rsi_short_lower.value) &
            (dataframe['volume_ratio'] > 1.15) &
            (dataframe['volume'] > 0)
        )

        # v4022: 熊市抄底做多条件（严格收紧版）
        # 条件：RSI深度超卖、价格在极低位、MACD金叉信号、资金流确认
        oversold_long = (
            (dataframe['rsi'] < 25) &  # v4018g: 35 -> 25 更严格超卖
            (dataframe['rsi_2'] < 20) &  # v4022新增: 快速RSI确认深度超卖
            (dataframe['rsi'] > dataframe['rsi'].shift(1)) &  # RSI开始反弹
            (dataframe['price_position'] < 20) &  # v4018g: 30 -> 20 价格在极低位
            (dataframe['mfi'] < 25) &  # v4022新增: 资金流确认超卖
            (dataframe['macdhist'] > dataframe['macdhist'].shift(1)) &  # MACD柱改善
            (dataframe['close'] > dataframe['close'].shift(1)) &  # 价格反弹
            (dataframe['volume'] > 0)
        )

        has_fib_data = 'fib_618' in dataframe.columns
        if has_fib_data:
            at_fib_support = dataframe['at_fib_618']
            at_fib_resist = dataframe['at_fib_382']

            long_adx_th_adj = long_adx_th - 2.0 * at_fib_support.astype(float) + 1.0 * (~at_fib_support).astype(float)
            short_adx_th_adj = short_adx_th - 2.0 * at_fib_resist.astype(float) + 1.0 * (~at_fib_resist).astype(float)

            long_entry = (
                major_bullish &
                minor_bullish &
                (dataframe['adx'] > long_adx_th_adj) &
                (dataframe['di_diff'] > long_di_th) &
                (dataframe['macdhist'] > 0) &
                (dataframe['rsi'] > self.buy_rsi_long_lower.value) &
                (dataframe['rsi'] < self.buy_rsi_long_upper.value) &
                (dataframe['volume_ratio'] > long_vol_th) &
                (dataframe['volume'] > 0)
            )

            short_entry = (
                major_bearish &
                minor_bearish &
                (dataframe['adx'] > short_adx_th_adj) &
                (dataframe['di_diff'] < -short_di_th) &
                (dataframe['macdhist'] < 0) &
                (dataframe['rsi'] < self.buy_rsi_short_upper.value) &
                (dataframe['rsi'] > self.buy_rsi_short_lower.value) &
                (dataframe['volume_ratio'] > 1.15) &
                (dataframe['volume'] > 0)
            )
        else:
            long_entry = long_entry_base
            short_entry = short_entry_base

        long_entry = long_entry & regime_stable
        short_entry = short_entry & regime_stable

        # v4016: 价格位置过滤 - 避免追高杀跌（放宽条件）
        # 做多时不在局部高点附近（价格位置<85%）
        # 做空时不在局部低点附近（价格位置>15%）
        long_entry = long_entry & (dataframe['price_position'] < 85)
        short_entry = short_entry & (dataframe['price_position'] > 15)

        # v4032: 多时间框架确认已完成
        # 1h EMA趋势已在major_bullish/major_bearish中使用
        # 1h RSI/MACD过滤经测试：
        #   - 温和条件：无效果（15m和1h信号高度相关）
        #   - 严格条件：回撤改善但利润下降
        # Bug已修复: 1h指标改用hourly后缀，列正确生成可供未来使用

        # v4030: 日线级别价格位置过滤（可选，默认关闭）
        # 避免在日线低点做空、日线高点做多
        # if 'daily_price_position' in dataframe.columns:
        #     long_entry = long_entry & (dataframe['daily_price_position'] > 20)
        #     short_entry = short_entry & (dataframe['daily_price_position'] > 15)

        # 根据市场状态过滤方向
        # v4016优化：熊市允许超卖抄底做多
        if market_regime == 'bullish':
            short_entry = short_entry & (dataframe['rsi'] > 70)
        elif market_regime == 'bearish':
            # 熊市：允许抄底做多信号
            long_entry = long_entry | oversold_long

        conflict_mask = long_entry & short_entry
        if conflict_mask.any():
            btc_regime = self._detect_market_regime(dataframe, pair)

            long_confirm = np.where(btc_regime == 'bullish', 2, 0)
            short_confirm = np.where(btc_regime == 'bearish', 2, 0)

            rsi = dataframe['rsi'].fillna(50)
            long_confirm = long_confirm + np.where(rsi < 40, 1, 0)
            short_confirm = short_confirm + np.where(rsi > 60, 1, 0)

            adx = dataframe['adx'].fillna(20)
            long_confirm = long_confirm + np.where(adx > 25, 1, 0)
            short_confirm = short_confirm + np.where(adx > 25, 1, 0)

            vol = dataframe['volume_ratio'].fillna(1.0)
            long_confirm = long_confirm + np.where(vol > 1.2, 1, 0)
            short_confirm = short_confirm + np.where(vol > 1.2, 1, 0)

            final_long = long_entry & ((long_confirm > short_confirm) | ((long_confirm == short_confirm) & (btc_regime == 'bullish')))
            final_short = short_entry & ((short_confirm > long_confirm) | ((long_confirm == short_confirm) & (btc_regime == 'bearish')))

            long_entry = final_long
            short_entry = final_short

        dataframe.loc[long_entry, 'enter_long'] = 1
        dataframe.loc[long_entry, 'enter_tag'] = f'v4014_long_{tier_name}_{market_regime}'

        dataframe.loc[short_entry, 'enter_short'] = 1
        dataframe.loc[short_entry, 'enter_tag'] = f'v4014_short_{tier_name}_{market_regime}'

        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe['exit_long'] = 0
        dataframe['exit_short'] = 0
        return dataframe

    def custom_stake_amount(self, pair: str, current_time: datetime, current_rate: float,
                            proposed_stake: float, min_stake: Optional[float], max_stake: float,
                            leverage: float, entry_tag: Optional[str], side: str,
                            **kwargs) -> float:
        if entry_tag == 'freqai_boost':
            return proposed_stake * 1.5
        else:
            return proposed_stake

    def custom_stoploss(
        self,
        pair: str,
        trade: Trade,
        current_time: datetime,
        current_rate: float,
        current_profit: float,
        after_fill: bool,
        **kwargs
    ) -> Optional[float]:
        # 硬止损保护
        if current_profit < -0.25:
            logger.warning(f"🚨 [硬止损] {pair} 亏损 {current_profit:.2%} > -25%")
            return 0.0

        try:
            open_trades = Trade.get_open_trades()
            if open_trades and len(open_trades) > 1:
                portfolio_profit = sum(t.close_profit_abs or 0 for t in open_trades)
                total_stake = sum(t.stake_amount for t in open_trades)
                portfolio_profit_pct = portfolio_profit / total_stake if total_stake > 0 else 0

                if portfolio_profit_pct < -0.10:
                    logger.warning(f"🚨 [组合止损] 组合亏损 {portfolio_profit_pct:.2%} > 10%")
                    return 0.0
        except:
            pass

        tier = self._get_pair_tier(pair)

        # 逆势交易使用更紧止损
        entry_tag = trade.enter_tag if trade.enter_tag else ''
        is_counter_trend = False
        if not trade.is_short and 'bearish' in entry_tag.lower():
            is_counter_trend = True  # 熊市做多
        elif trade.is_short and 'bullish' in entry_tag.lower():
            is_counter_trend = True  # 牛市做空

        if is_counter_trend:
            # 逆势交易：固定8%止损，不随时间放宽
            initial_stoploss = 0.08
        else:
            # 顺势交易：使用分层止损
            if tier == 1:
                initial_stoploss = self.tier1_initial_stoploss  # 18%
            elif tier == 2:
                initial_stoploss = self.tier2_initial_stoploss  # 15%
            elif tier == 3:
                initial_stoploss = self.tier3_initial_stoploss  # 12%
            else:
                initial_stoploss = self.tier4_initial_stoploss  # 10%

        # v4017优化: 时间敏感止损
        # 分析显示: 亏损交易平均持仓4.6天，盈利交易0.8天
        # 解决方案: 持仓时间过长时收紧止损，避免亏损加深
        holding_hours = (current_time - trade.open_date_utc).total_seconds() / 3600

        # 持仓超过24小时且处于亏损，止损收紧20%
        if holding_hours > 24 and current_profit < 0:
            initial_stoploss = initial_stoploss * 0.8
            if holding_hours > 24:  # 只记录一次
                logger.info(f"⏰ [24h止损收紧] {pair} 持仓{holding_hours:.0f}h亏损{current_profit:.2%}, 止损收紧到{initial_stoploss:.2%}")

        # 持仓超过48小时且处于亏损，止损再收紧20%
        if holding_hours > 48 and current_profit < 0:
            initial_stoploss = initial_stoploss * 0.8
            logger.info(f"⏰ [48h止损收紧] {pair} 持仓{holding_hours:.0f}h亏损{current_profit:.2%}, 止损收紧到{initial_stoploss:.2%}")

        # 持仓超过72小时且亏损超过5%，强制止损
        if holding_hours > 72 and current_profit < -0.05:
            logger.warning(f"🚨 [72h强制止损] {pair} 持仓{holding_hours:.0f}h亏损{current_profit:.2%}, 强制退出")
            return 0.001  # 微小止损触发平仓

        if trade.is_short:
            return initial_stoploss
        else:
            return -initial_stoploss

    def adjust_trade_position(
        self,
        trade: Trade,
        current_time: datetime,
        current_rate: float,
        current_profit: float,
        min_stake: float | None,
        max_stake: float,
        current_entry_rate: float,
        current_exit_rate: float,
        current_entry_profit: float,
        current_exit_profit: float,
        **kwargs
    ) -> float | None | tuple[float | None, str | None]:
        if trade.has_open_orders:
            return None

        dataframe, _ = self.dp.get_analyzed_dataframe(trade.pair, self.timeframe)
        if dataframe is None or dataframe.empty:
            return None

        tier = self._get_pair_tier(trade.pair)
        if tier == 1:
            profit_targets = self.tier1_profit_targets
        elif tier == 2:
            profit_targets = self.tier2_profit_targets
        elif tier == 3:
            profit_targets = self.tier3_profit_targets
        else:
            profit_targets = self.tier4_profit_targets

        trade_id = trade.id
        if trade_id not in self._profit_tier_cache:
            self._profit_tier_cache[trade_id] = {"tier_hit": 0, "initial_stake": trade.stake_amount}

        profit_state = self._profit_tier_cache[trade_id]

        current_tier = profit_state["tier_hit"]
        if current_tier < len(profit_targets):
            target_profit = profit_targets[current_tier]
            if current_profit >= target_profit:
                profit_state["tier_hit"] += 1
                reduce_amount = trade.stake_amount / 3

                if min_stake and reduce_amount < min_stake:
                    return None

                logger.info(f"🎯 [分层止盈] {trade.pair} 第{profit_state['tier_hit']}档 {target_profit:.1%}")
                return -reduce_amount, f"profit_take_tier{profit_state['tier_hit']}"

        return None

    def custom_exit(
        self,
        pair: str,
        trade: Trade,
        current_time: datetime,
        current_rate: float,
        current_profit: float,
        **kwargs
    ) -> Optional[str]:
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        if dataframe is None or len(dataframe) < 2:
            return None

        last_candle = dataframe.iloc[-1]
        prev_candle = dataframe.iloc[-2]

        # Trailing Stop (利润锁定)
        if not hasattr(self, '_trade_high_profit'):
            self._trade_high_profit = {}
        trade_id = trade.id
        if trade_id not in self._trade_high_profit:
            self._trade_high_profit[trade_id] = current_profit
        else:
            if current_profit > self._trade_high_profit[trade_id]:
                self._trade_high_profit[trade_id] = current_profit

        high_profit = self._trade_high_profit.get(trade_id, current_profit)

        # v4032: ATR动态止盈 - 反向逻辑：高波动收紧(快获利)、低波动放宽(耐心等待)
        # 因为高波动时价格容易反转，需要更快锁定利润
        atr_pct = last_candle.get('atr_pct', 0.02)
        if atr_pct > 0.035:  # 高波动(>3.5%) - 快速获利，收紧阈值
            atr_profit_lock_threshold = self.sell_profit_lock_threshold.value * 0.85
        elif atr_pct < 0.02:  # 低波动(<2%) - 稳定行情，放宽等待
            atr_profit_lock_threshold = self.sell_profit_lock_threshold.value * 1.2
        else:
            atr_profit_lock_threshold = self.sell_profit_lock_threshold.value

        # Trailing Stop (利润锁定) - v4032: 使用ATR动态阈值
        if high_profit > atr_profit_lock_threshold:
            drawdown = (high_profit - current_profit) / high_profit
            if drawdown > (1 - self.sell_profit_lock_ratio.value):
                return 'trailing_stop_exit'

        # 获取指标
        adx = last_candle.get('adx', 0)
        rsi = last_candle.get('rsi', 50)
        rsi_prev = prev_candle.get('rsi', 50)
        di_diff = last_candle.get('di_diff', 0)
        di_diff_prev = prev_candle.get('di_diff', 0)
        macdhist = last_candle.get('macdhist', 0)
        macdhist_prev = prev_candle.get('macdhist', 0)
        ema20 = last_candle.get('ema_20', 0)
        ema50 = last_candle.get('ema_50', 0)
        ema20_prev = prev_candle.get('ema_20', 0)
        ema50_prev = prev_candle.get('ema_50', 0)

        # ===== v4030: 趋势反转动态出场 =====
        # 核心思路: 基于趋势反转信号出场，而不是固定阈值
        # 关键: 必须有强反转信号才出场，避免过早离场

        # 计算趋势反转强度 (0-100分)
        if trade.is_short:
            # 做空趋势反转信号检测
            trend_reversal_score = 0

            # 1. RSI超卖反弹 (强信号) - 必须满足
            # RSI从高位下跌到<25才是真正的超卖反弹
            rsi_oversold = rsi < 25
            rsi_bounce = rsi < 30 and rsi > rsi_prev and rsi_prev < 25

            if rsi_oversold:
                trend_reversal_score += 50  # 超卖反弹信号
            elif rsi_bounce:
                trend_reversal_score += 35  # RSI开始反弹

            # 2. DI转向 (多头力量增强) - 必须满足
            di_turning_positive = di_diff > 0 and di_diff_prev <= 0
            if di_turning_positive:
                trend_reversal_score += 30  # DI刚转正
            elif di_diff > 5:
                trend_reversal_score += 15  # DI明显转正

            # 3. MACD转向 (动能转正)
            if macdhist > 0 and macdhist_prev <= 0:
                trend_reversal_score += 20  # MACD刚转正

            # 4. EMA金叉 (趋势反转确认)
            ema_cross_up = ema20 > ema50 and ema20_prev <= ema50_prev
            if ema_cross_up:
                trend_reversal_score += 15  # EMA刚金叉

            # 趋势反转出场条件 - 更严格
            # 条件1: 有盈利 + RSI超卖 + DI转正 (最强信号)
            # 条件2: 有盈利 + RSI反弹 + DI转正 + MACD转正 (确认信号)
            strong_reversal = (rsi_oversold or rsi_bounce) and (di_turning_positive or di_diff > 5)

            if current_profit > 0.005 and trend_reversal_score >= 80:
                logger.info(f"🔄 [强趋势反转做空] {pair} 利润{current_profit:.1%} 反转分{trend_reversal_score} RSI={rsi:.1f}")
                return 'trend_reversal_exit'
            if current_profit > 0.02 and strong_reversal and trend_reversal_score >= 65:
                logger.info(f"🔄 [趋势反转做空] {pair} 利润{current_profit:.1%} 反转分{trend_reversal_score} RSI={rsi:.1f}")
                return 'trend_reversal_exit'

        else:
            # 做多趋势反转信号检测
            trend_reversal_score = 0

            # 1. RSI超买回落 (强信号) - 必须满足
            rsi_overbought = rsi > 75
            rsi_decline = rsi > 70 and rsi < rsi_prev and rsi_prev > 75

            if rsi_overbought:
                trend_reversal_score += 50  # 超买回落信号
            elif rsi_decline:
                trend_reversal_score += 35  # RSI开始回落

            # 2. DI转向 (空头力量增强) - 必须满足
            di_turning_negative = di_diff < 0 and di_diff_prev >= 0
            if di_turning_negative:
                trend_reversal_score += 30  # DI刚转负
            elif di_diff < -5:
                trend_reversal_score += 15  # DI明显转负

            # 3. MACD转向 (动能转负)
            if macdhist < 0 and macdhist_prev >= 0:
                trend_reversal_score += 20  # MACD刚转负

            # 4. EMA死叉 (趋势反转确认)
            ema_cross_down = ema20 < ema50 and ema20_prev >= ema50_prev
            if ema_cross_down:
                trend_reversal_score += 15  # EMA刚死叉

            # 趋势反转出场条件 - 更严格
            strong_reversal = (rsi_overbought or rsi_decline) and (di_turning_negative or di_diff < -5)

            if current_profit > 0.005 and trend_reversal_score >= 80:
                logger.info(f"🔄 [强趋势反转做多] {pair} 利润{current_profit:.1%} 反转分{trend_reversal_score} RSI={rsi:.1f}")
                return 'trend_reversal_exit'
            if current_profit > 0.02 and strong_reversal and trend_reversal_score >= 65:
                logger.info(f"🔄 [趋势反转做多] {pair} 利润{current_profit:.1%} 反转分{trend_reversal_score} RSI={rsi:.1f}")
                return 'trend_reversal_exit'

        # ===== 逆势交易快速离场逻辑 =====
        entry_tag = trade.enter_tag if trade.enter_tag else ''
        is_counter_trend = False
        if not trade.is_short and 'bearish' in entry_tag.lower():
            is_counter_trend = True
        elif trade.is_short and 'bullish' in entry_tag.lower():
            is_counter_trend = True

        if is_counter_trend:
            if high_profit > 0.015 and current_profit > 0:
                drawdown_from_high = (high_profit - current_profit) / high_profit if high_profit > 0 else 0
                if not trade.is_short:
                    if di_diff < -25 and drawdown_from_high > 0.40:
                        return 'counter_trend_trend_worsen'
                else:
                    if di_diff > 25 and drawdown_from_high > 0.40:
                        return 'counter_trend_trend_worsen'

        # 强逆势止损
        if adx > 35 and current_profit > 0.01:
            if not trade.is_short and di_diff < -20:
                return 'follow_market_stop_loss'
            if trade.is_short and di_diff > 20:
                return 'follow_market_stop_loss'

        # 原有的level退出逻辑（作为保底）
        reverse_signals = 0
        market_regime = self._detect_market_regime(dataframe, pair)

        if not trade.is_short:
            if last_candle["ema_20"] < last_candle["ema_50"]:
                reverse_signals += 1
            if last_candle["macdhist"] < 0:
                reverse_signals += 1
            if last_candle["minus_di"] > last_candle["plus_di"]:
                reverse_signals += 1
            if last_candle["rsi"] > self.sell_rsi_overbought.value:
                reverse_signals += 1
        else:
            if last_candle["ema_20"] > last_candle["ema_50"]:
                reverse_signals += 1
            if last_candle["macdhist"] > 0:
                reverse_signals += 1
            if last_candle["plus_di"] > last_candle["minus_di"]:
                reverse_signals += 1
            if market_regime != 'bearish':
                if last_candle["rsi"] < self.sell_rsi_oversold.value:
                    reverse_signals += 1
            else:
                if last_candle["rsi"] > self.sell_rsi_overbought.value:
                    reverse_signals += 1

        adx_weak = self.sell_adx_weak_threshold.value

        # level退出（保底逻辑）
        if 0 < current_profit < 0.05 and reverse_signals >= 4:
            return 'level1_profit_exit'

        if 0.05 <= current_profit < 0.08 and reverse_signals >= 4:
            return 'level2_profit_exit'

        if 0.08 <= current_profit < 0.15 and reverse_signals >= 4 and adx < adx_weak + 5:
            return 'level3_profit_exit'

        if current_profit >= 0.15 and reverse_signals >= 4 and adx < adx_weak:
            return 'level4_trailing_exit'

        if -0.05 < current_profit <= 0 and reverse_signals >= 4:
            return 'small_loss_exit'

        if -0.10 < current_profit <= -0.05 and reverse_signals >= 4 and adx < 25:
            return 'medium_loss_exit'

        if current_profit <= -0.10:
            return 'big_loss_exit'

        return None

    def leverage(
        self,
        pair: str,
        current_time: datetime,
        current_rate: float,
        proposed_leverage: float,
        max_leverage: float,
        entry_tag: Optional[str],
        side: str,
        **kwargs
    ) -> float:
        return 1

    def _is_backtesting(self) -> bool:
        if hasattr(self.dp, 'runmode'):
            from freqtrade.enums import RunMode
            return self.dp.runmode in (RunMode.BACKTEST, RunMode.HYPEROPT)
        return False

    def confirm_trade_entry(
        self,
        pair: str,
        order_type: str,
        amount: float,
        rate: float,
        time_in_force: str,
        current_time: datetime,
        entry_tag: Optional[str],
        side: str,
        **kwargs
    ) -> bool:
        trades = Trade.get_open_trades()
        if trades:
            long_trades = [t for t in trades if not t.is_short]
            short_trades = [t for t in trades if t.is_short]

            max_per_direction = max(1, self.max_open_trades // 2)
            long_count = len(long_trades)
            short_count = len(short_trades)

            if side == 'long' and long_count >= max_per_direction:
                return False

            if side == 'short' and short_count >= max_per_direction:
                return False

        is_backtest = self._is_backtesting()
        if is_backtest:
            dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
            if dataframe is not None and not dataframe.empty:
                last_candle = dataframe.iloc[-1]
                if self.freqai_enabled and "do_predict" in last_candle:
                    if last_candle["do_predict"] != 1:
                        return False
                if 'rsi' in last_candle:
                    if side == 'long' and last_candle['rsi'] > 80:
                        return False
                    if side == 'short' and last_candle['rsi'] < 20:
                        return False
            return True

        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        if dataframe is None or dataframe.empty:
            return True

        last_candle = dataframe.iloc[-1]

        if self.freqai_enabled and "do_predict" in last_candle:
            if last_candle["do_predict"] != 1:
                return False

        if 'atr_pct' in last_candle and last_candle['atr_pct'] > 0.04:
            return False

        if 'adx' in last_candle and last_candle['adx'] < 15:
            return False

        if 'rsi' in last_candle:
            if side == 'long' and last_candle['rsi'] > 80:
                return False
            if side == 'short' and last_candle['rsi'] < 20:
                return False

        if 'momentum_5' in last_candle:
            if side == 'long' and last_candle['momentum_5'] < -0.01:
                return False
            if side == 'short' and last_candle['momentum_5'] > 0.01:
                return False

        if 'di_diff' in last_candle:
            if side == 'long' and last_candle['di_diff'] < 0:
                return False
            if side == 'short' and last_candle['di_diff'] > 0:
                return False

        # v4032: 链上数据过滤 - 资金费率极端时拒绝入场
        if not is_backtest and FREE_ONCHAIN_AVAILABLE and self.enable_onchain_filter:
            try:
                # 获取BTC资金费率作为市场整体参考
                funding_data = get_funding_rate("BTCUSDT")
                funding_rate_pct = funding_data.get('rate_pct', 0)

                # 资金费率极端正值(>0.05%)时拒绝做多 - 市场过热
                if side == 'long' and funding_rate_pct > 0.05:
                    logger.info(f"🚫 [链上过滤] {pair} 做多被拒绝 - 资金费率过热 {funding_rate_pct:.3f}%")
                    return False

                # 资金费率极端负值(<-0.05%)时拒绝做空 - 市场过冷
                if side == 'short' and funding_rate_pct < -0.05:
                    logger.info(f"🚫 [链上过滤] {pair} 做空被拒绝 - 资金费率过冷 {funding_rate_pct:.3f}%")
                    return False

                # 获取多空比
                ratio_data = get_long_short_ratio("BTC")
                long_ratio = ratio_data.get('long_ratio', 0.5)

                # 多空比极端(>0.75)时拒绝做多 - 过多头寸
                if side == 'long' and long_ratio > 0.75:
                    logger.info(f"🚫 [链上过滤] {pair} 做多被拒绝 - 多空比过高 {long_ratio:.2f}")
                    return False

                # 多空比极端(<0.25)时拒绝做空 - 过多空头寸
                if side == 'short' and long_ratio < 0.25:
                    logger.info(f"🚫 [链上过滤] {pair} 做空被拒绝 - 多空比过低 {long_ratio:.2f}")
                    return False
            except Exception as e:
                logger.warning(f"链上数据获取失败: {e}, 跳过过滤")

        return True

    def confirm_trade_exit(
        self,
        pair: str,
        trade: Trade,
        order_type: str,
        amount: float,
        rate: float,
        time_in_force: str,
        exit_reason: str,
        current_time: datetime,
        **kwargs
    ) -> bool:
        """
        v4018g: 出场确认 - 拒绝trailing_stop当利润小且趋势延续

        核心思路:
        - trailing_stop_exit利润小(<3%)时，如果趋势方向仍对，拒绝退出让利润跑
        - 其他所有退出立即确认（包括止损、level退出等）
        """
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        if dataframe is None or dataframe.empty:
            return True

        last_candle = dataframe.iloc[-1]
        current_profit = (rate - trade.open_rate) / trade.open_rate
        if trade.is_short:
            current_profit = -current_profit

        # 止损/大亏损/紧急 - 立即确认
        if exit_reason in ['stop_loss', 'stoploss_on_exchange', 'emergency_exit', 'big_loss_exit']:
            return True

        # level2/level3/level4 利润退出 - 立即锁定（利润够大）
        if exit_reason in ['level2_profit_exit', 'level3_profit_exit', 'level4_trailing_exit']:
            return True

        # trailing_stop_exit 利润<3% 且趋势延续时拒绝
        if exit_reason == 'trailing_stop_exit' and current_profit < 0.03:
            rsi = last_candle.get('rsi', 50)
            adx = last_candle.get('adx', 0)
            di_diff = last_candle.get('plus_di', 0) - last_candle.get('minus_di', 0)

            if trade.is_short:
                # 做空趋势延续: ADX>20, DI负(空头), RSI不极端(<70)
                if adx > 20 and di_diff < 0 and rsi < 70:
                    logger.info(f"🔒 [拒绝trailing] {pair} 做空趋势延续 利润{current_profit:.1%} ADX={adx:.1f}")
                    return False
            else:
                # 做多趋势延续: ADX>20, DI正(多头), RSI不极端(>30)
                if adx > 20 and di_diff > 0 and rsi > 30:
                    logger.info(f"🔒 [拒绝trailing] {pair} 做多趋势延续 利润{current_profit:.1%} ADX={adx:.1f}")
                    return False

        # v4032: 亏损时价格在局部低点拒绝trailing stop，避免卖在最低点
        if exit_reason == 'trailing_stop_exit' and current_profit < 0:
            rsi = last_candle.get('rsi', 50)
            price_position = last_candle.get('price_position', 50)
            # 做多亏损时，RSI超卖(<35)或价格在低位(<25%)时拒绝，等待反弹
            if not trade.is_short and (rsi < 35 or price_position < 25):
                logger.info(f"🔒 [拒绝底部止损] {pair} 做多亏损{current_profit:.1%} RSI={rsi:.0f} 位置={price_position:.0f}%")
                return False

        return True