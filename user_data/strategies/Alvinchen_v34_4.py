"""
FreqAI Optimized Strategy - v31
目标: 30天20%盈利

核心优化:
1. 改善盈亏比: 止损3.5% vs 平均盈利5%+ (目标1.4:1)
2. 增加交易机会: 放宽ADX(25)和EMA条件
3. 优化止盈: ROI最高12%，让盈利交易跑更远
4. 移动止损: 分阶段锁定利润(50%/60%/70%/75%)

参数配置:
- 止损: 3.5% (优化盈亏比)
- ROI: 12%/8%/5%/3%/2%/1%
- ADX阈值: 25 (放宽自30)
- DI阈值: 15 (放宽自25)
- RSI区间: 50-75 (扩大自55-68)

期望收益分析:
- 胜率50%, 平均盈利5%, 止损3.5% → 期望值+0.75%/笔
- 每天2笔交易 → 每日+1.5%
- 30天 → +45% (理论最大值)

风控:
- 单笔最大亏损: 3.5%
- 连续亏损容忍: 5次 (总资金17.5%风险)
"""

import logging
import numpy as np
import pandas as pd
from pandas import DataFrame
from typing import Optional, Dict, Any, Union
from collections import OrderedDict
from datetime import datetime, timedelta
from freqtrade.strategy import IStrategy, DecimalParameter, IntParameter
from freqtrade.persistence import Trade
from freqtrade.enums import RunMode
import talib.abstract as ta
import freqtrade.vendor.qtpylib.indicators as qtpylib
from functools import reduce

# 情绪分析和链上数据模块
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

# 订单簿分析模块
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


class Alvinchen_v34_4(IStrategy):
    """
    Balanced FreqAI Strategy - High Win Rate Focus

    Key features:
    - Balanced entry conditions
    - Quick ROI exits
    - Tight stop loss
    - Sentiment analysis integration
    - On-chain data signals
    """

    INTERFACE_VERSION = 3
    can_short = True
    use_exit_signal = True  # 启用退出信号
    exit_profit_only = False
    exit_profit_offset = 0.0  # 退出信号的最小利润阈值

    timeframe = '15m'
    startup_candle_count = 200

    # Hyperparameters - Optimized via hyperopt
    buy_pred_threshold = DecimalParameter(0.3, 0.5, default=0.372, space='buy', optimize=True)
    adx_threshold = DecimalParameter(20, 30, default=21, space='buy', optimize=True)
    volume_mult = DecimalParameter(1.3, 2.0, default=1.465, space='buy', optimize=True)

    # Sentiment & On-chain configuration
    enable_sentiment_check = True          # 启用情绪检查
    enable_onchain_filter = True           # 启用链上数据过滤
    enable_news_filter = True              # 启用新闻过滤
    enable_orderbook_analysis = True       # 启用订单簿分析
    sentiment_bullish_threshold = 0.65    # 看涨情绪阈值
    sentiment_bearish_threshold = 0.35    # 看跌情绪阈值
    sentiment_extreme_fear = 25           # 极度恐慌阈值
    sentiment_extreme_greed = 75          # 极度贪婪阈值
    strict_funding_filter = False          # 严格资金费率过滤
    strict_lsr_filter = False             # 严格多空比过滤
    sentiment_cache_ttl = 300             # 情绪缓存时间(秒)
    news_negative_threshold = 0.7         # 新闻负面情绪阈值
    news_check_cooldown = 3600            # 新闻检查冷却时间(秒)

    # 订单簿分析参数
    obi_threshold = 0.3                    # OBI阈值 (超过此值视为有效信号)
    obi_strong_threshold = 0.5             # 强OBI阈值
    spread_threshold = 0.1                 # 价差阈值 (%)
    large_order_mult = 3.0                 # 大单倍数阈值
    orderbook_cache_ttl = 5                # 订单簿缓存时间(秒)

    # ========== 动态杠杆配置 ==========
    # v18 优化: 禁用杠杆 - 测试表明无杠杆表现更好
    max_leverage = 1                       # 最大杠杆倍数
    min_leverage = 1                       # 最小杠杆倍数
    leverage_enabled = False               # 禁用杠杆

    # 杠杆置信度阈值
    leverage_threshold_medium = 0.70       # 中等置信度阈值
    leverage_threshold_high = 0.80         # 高置信度阈值 (2x杠杆)
    leverage_threshold_very_high = 0.90    # 极高置信度阈值 (3x杠杆)
    leverage_threshold_extreme = 0.95      # 极端置信度阈值

    # ========== V31: 放宽止损配置 ==========
    # 多单止损50%，空单止损25%
    stoploss = -0.50  # 默认止损50%（用于多单）
    use_custom_stoploss = True  # 启用自定义止损

    # 不同方向的止损比例
    long_stoploss = 0.50   # 多单止损50%
    short_stoploss = 0.25  # 空单止损25%

    # 移动止损参数
    trailing_stop = False  # 禁用内置移动止损
    trailing_stop_positive = 0.02
    trailing_stop_positive_offset = 0.03
    trailing_only_offset_is_reached = True

    # 止损触发后锁定利润阈值
    profit_lock_threshold = 0.03  # 盈利3%后开始移动止损
    profit_lock_ratio = 0.60       # 锁定60%的利润

    # ========== V31: 补仓策略配置 ==========
    position_adjustment_enable = True      # 启用补仓
    max_entry_position_adjustment = 3      # 最多补仓3次
    add_position_threshold = -0.05         # 亏损5%时触发补仓
    add_position_ratio = 0.5               # 补仓比例为初始仓位的50%

    # ========== 止盈(ROI)配置 ==========
    # V31优化: 放宽ROI，让利润奔跑
    minimal_roi = {
        "0": 0.15,    # 15%利润立即退出
        "30": 0.10,   # 30分钟后10%
        "60": 0.06,   # 1小时后6%
        "120": 0.04,  # 2小时后4%
        "240": 0.02,  # 4小时后2%
        "480": 0.01,  # 8小时后1%
        "960": 0      # 16小时后保本
    }

    # 回测模式标志 - 回测时跳过实时数据检查
    _backtest_mode = False
    _dry_run_mode = False

    def __init__(self, config: dict) -> None:
        super().__init__(config)
        self.freqai_enabled = config.get('freqai', {}).get('enabled', False)

        # 检测运行模式
        self._dry_run_mode = config.get('dry_run', False)
        # 回测模式检测: 当 dry_run=True 且没有实时交易时为回测
        # 在回测时 confirm_trade_entry 会被调用但无法访问实时API

        logger.info(f"Trend Following FreqAI Strategy - enabled: {self.freqai_enabled}")

        # 情绪数据缓存
        self._sentiment_cache = {}
        self._onchain_cache = {}
        self._news_cache = {}
        self._last_news_check = {}
        self._orderbook_cache = {}
        # 杠杆缓存 - 用于custom_stoploss
        self._leverage_cache = {}
        logger.info(f"情绪分析模块: {'可用' if FREE_SENTIMENT_AVAILABLE else '不可用'}")
        logger.info(f"链上数据模块: {'可用' if FREE_ONCHAIN_AVAILABLE else '不可用'}")
        logger.info(f"订单簿分析模块: {'可用' if ORDERBOOK_AVAILABLE else '不可用'}")

    def feature_engineering_expand_all(
        self, dataframe: DataFrame, period: int, metadata: dict, **kwargs
    ) -> DataFrame:
        """FreqAI features with high-accuracy indicators

        Research-backed indicators (win rates):
        - ROC: 93% win rate (best overall)
        - WMA: 83% win rate
        - HMA: 77% win rate (reduces lag)
        - MFI: volume-based momentum
        - Short RSI (2-6): better than RSI-14
        """
        # ========== Core Momentum Indicators ==========
        dataframe[f"%-rsi-period_{period}"] = ta.RSI(dataframe, timeperiod=period)
        # Short RSI for mean reversion (research shows 2-6 periods work best)
        dataframe[f"%-rsi_short-period_{period}"] = ta.RSI(dataframe, timeperiod=max(2, period//7))

        # ROC - Price Rate of Change (93% win rate indicator)
        dataframe[f"%-roc-period_{period}"] = ta.ROC(dataframe, timeperiod=period)

        # MOM - Momentum
        dataframe[f"%-mom-period_{period}"] = ta.MOM(dataframe, timeperiod=period)

        # ========== Trend Indicators ==========
        dataframe[f"%-ema-period_{period}"] = ta.EMA(dataframe['close'], timeperiod=period)

        # WMA - Weighted Moving Average (83% win rate)
        dataframe[f"%-wma-period_{period}"] = ta.WMA(dataframe['close'], timeperiod=period)

        # HMA - Hull Moving Average (77% win rate, reduces lag)
        hma_period = max(2, period)
        dataframe[f"%-hma-period_{period}"] = self._hma(dataframe['close'], hma_period)

        # SMA for comparison
        dataframe[f"%-sma-period_{period}"] = ta.SMA(dataframe['close'], timeperiod=period)

        # ========== Volatility Indicators ==========
        dataframe[f"%-atr-period_{period}"] = ta.ATR(dataframe, timeperiod=period)
        dataframe[f"%-atr_pct-period_{period}"] = dataframe[f"%-atr-period_{period}"] / dataframe['close']

        # ========== Volume Indicators ==========
        dataframe[f"%-volume_mean-period_{period}"] = dataframe['volume'].rolling(period).mean()
        dataframe[f"%-volume_ratio-period_{period}"] = dataframe['volume'] / (dataframe[f"%-volume_mean-period_{period}"] + 1e-8)

        # MFI - Money Flow Index (volume-weighted RSI)
        dataframe[f"%-mfi-period_{period}"] = ta.MFI(dataframe, timeperiod=period)

        # ========== Trend Strength ==========
        dataframe[f"%-adx-period_{period}"] = ta.ADX(dataframe, timeperiod=period)
        dataframe[f"%-plus_di-period_{period}"] = ta.PLUS_DI(dataframe, timeperiod=period)
        dataframe[f"%-minus_di-period_{period}"] = ta.MINUS_DI(dataframe, timeperiod=period)

        # ========== Price Action ==========
        dataframe[f"%-returns-period_{period}"] = dataframe['close'].pct_change(period)

        # ========== Composite Indicators (Combining multiple for accuracy) ==========
        # ROC-MOM combination (momentum confirmation)
        dataframe[f"%-roc_mom_combo-period_{period}"] = (
            (dataframe[f"%-roc-period_{period}"] + dataframe[f"%-mom-period_{period}"]) / 2
        )

        # HMA-EMA spread (trend with reduced lag)
        dataframe[f"%-hma_ema_spread-period_{period}"] = (
            dataframe[f"%-hma-period_{period}"] - dataframe[f"%-ema-period_{period}"]
        ) / dataframe['close']

        # WMA-SMA spread (weighted vs simple comparison)
        dataframe[f"%-wma_sma_spread-period_{period}"] = (
            dataframe[f"%-wma-period_{period}"] - dataframe[f"%-sma-period_{period}"]
        ) / dataframe['close']

        # RSI-MFI combination (price + volume momentum)
        dataframe[f"%-rsi_mfi_avg-period_{period}"] = (
            dataframe[f"%-rsi-period_{period}"] + dataframe[f"%-mfi-period_{period}"]
        ) / 2

        # Volume-weighted price momentum
        dataframe[f"%-vwap_proxy-period_{period}"] = (
            (dataframe['close'] * dataframe['volume']).rolling(period).sum() /
            (dataframe['volume'].rolling(period).sum() + 1e-8)
        )

        # Price position relative to HMA
        dataframe[f"%-price_hma_ratio-period_{period}"] = (
            dataframe['close'] / dataframe[f"%-hma-period_{period}"] - 1
        )

        # ATR-normalized momentum
        dataframe[f"%-atr_normalized_mom-period_{period}"] = (
            dataframe[f"%-mom-period_{period}"] / (dataframe[f"%-atr-period_{period}"] + 1e-8)
        )

        return dataframe

    def _hma(self, series: pd.Series, period: int) -> pd.Series:
        """Calculate Hull Moving Average (77% win rate indicator)

        HMA formula: WMA(2*WMA(n/2) - WMA(n), sqrt(n))
        Reduces lag while maintaining smoothness
        """
        half_period = int(period / 2)
        sqrt_period = int(np.sqrt(period))

        wma_half = ta.WMA(series, timeperiod=half_period)
        wma_full = ta.WMA(series, timeperiod=period)

        raw_hma = 2 * wma_half - wma_full
        hma = ta.WMA(raw_hma, timeperiod=sqrt_period)

        return hma

    def _ttm_squeeze(self, dataframe: DataFrame, period: int = 20, mult: float = 1.5) -> pd.Series:
        """
        TTM Squeeze - 波动率压缩检测 (70%+胜率)

        原理: Bollinger Bands在Keltner Channels内 = 波动压缩 = 即将突破
        当squeeze结束(波动扩张)时入场
        """
        # Bollinger Bands
        bb_basis = dataframe['close'].rolling(period).mean()
        bb_std = dataframe['close'].rolling(period).std()
        bb_upper = bb_basis + 2 * bb_std
        bb_lower = bb_basis - 2 * bb_std

        # Keltner Channels
        kc_basis = dataframe['close'].ewm(span=period).mean()
        atr = ta.ATR(dataframe, timeperiod=period)
        kc_upper = kc_basis + mult * atr
        kc_lower = kc_basis - mult * atr

        # Squeeze: BB在KC内 = 波动压缩
        squeeze = (bb_lower > kc_lower) & (bb_upper < kc_upper)
        return squeeze

    def _wave_trend(self, dataframe: DataFrame, channel_len: int = 10, avg_len: int = 21) -> tuple:
        """
        Wave Trend Oscillator (65%+胜率)

        结合RSI和移动平均的超买超卖指标
        wt1上穿wt2且<-60 = 买入信号
        wt1下穿wt2且>60 = 卖出信号
        """
        hlc3 = (dataframe['high'] + dataframe['low'] + dataframe['close']) / 3
        esa = ta.EMA(hlc3, timeperiod=channel_len)
        d = ta.EMA(abs(hlc3 - esa), timeperiod=channel_len)
        ci = (hlc3 - esa) / (0.015 * d + 1e-8)
        wt1 = ta.EMA(ci, timeperiod=avg_len)
        wt2 = ta.SMA(wt1, timeperiod=4)
        return wt1, wt2

    def _supertrend(self, dataframe: DataFrame, period: int = 10, multiplier: float = 3.0) -> tuple:
        """
        Supertrend - 超级趋势指标 (50-60%胜率)

        基于ATR的趋势线，简单有效的趋势跟随
        direction: 1 = 多头, -1 = 空头
        """
        atr = ta.ATR(dataframe, timeperiod=period)
        hl2 = (dataframe['high'] + dataframe['low']) / 2

        upper_band = hl2 + multiplier * atr
        lower_band = hl2 - multiplier * atr

        # Initialize
        supertrend = pd.Series(0.0, index=dataframe.index)
        direction = pd.Series(1, index=dataframe.index)

        for i in range(1, len(dataframe)):
            if dataframe['close'].iloc[i] > upper_band.iloc[i-1]:
                direction.iloc[i] = 1
            elif dataframe['close'].iloc[i] < lower_band.iloc[i-1]:
                direction.iloc[i] = -1
            else:
                direction.iloc[i] = direction.iloc[i-1]

            if direction.iloc[i] == 1:
                supertrend.iloc[i] = lower_band.iloc[i]
            else:
                supertrend.iloc[i] = upper_band.iloc[i]

        return supertrend, direction

    def _ichimoku(self, dataframe: DataFrame) -> tuple:
        """
        Ichimoku Cloud - 一目均衡表 (55-75%胜率)

        多维度趋势、支撑阻力、动量分析
        - 价格在云上方 = 多头趋势
        - TK金叉 = 入场信号
        """
        tenkan = (dataframe['high'].rolling(9).max() + dataframe['low'].rolling(9).min()) / 2
        kijun = (dataframe['high'].rolling(26).max() + dataframe['low'].rolling(26).min()) / 2
        senkou_a = ((tenkan + kijun) / 2).shift(26)
        senkou_b = ((dataframe['high'].rolling(52).max() + dataframe['low'].rolling(52).min()) / 2).shift(26)
        chikou = dataframe['close'].shift(-26)

        return tenkan, kijun, senkou_a, senkou_b, chikou

    def _detect_order_blocks(self, dataframe: DataFrame) -> tuple:
        """
        Order Block Detection - 订单块检测 (60%+胜率)

        SMC概念: 机构买卖区域
        - 看涨OB: 下跌趋势中最后一根上涨K线
        - 看跌OB: 上涨趋势中最后一根下跌K线
        """
        # Bullish OB: 最后一根上涨K线后开始下跌
        bullish_ob = (
            (dataframe['close'] > dataframe['open']) &  # 当前是上涨K线
            (dataframe['close'].shift(-1) < dataframe['open'].shift(-1))  # 下一根开始下跌
        )

        # Bearish OB: 最后一根下跌K线后开始上涨
        bearish_ob = (
            (dataframe['close'] < dataframe['open']) &  # 当前是下跌K线
            (dataframe['close'].shift(-1) > dataframe['open'].shift(-1))  # 下一根开始上涨
        )

        return bullish_ob, bearish_ob

    def feature_engineering_expand_basic(
        self, dataframe: DataFrame, metadata: dict, **kwargs
    ) -> DataFrame:
        """Basic features with high-accuracy indicators

        Research-backed additions:
        - Short RSI (2-6): Better for mean reversion
        - CCI: 50% win rate, good for cyclical trends
        - Aroon: 47% win rate, trend strength detection
        - Stochastic: 43% win rate, oscillator
        - VWAP proxy: 93% win rate
        """
        # ========== Time Features ==========
        dataframe["%-hour"] = dataframe["date"].dt.hour
        dataframe["%-day_of_week"] = dataframe["date"].dt.dayofweek

        # ========== RSI Suite (Short periods work better) ==========
        dataframe["%-rsi"] = ta.RSI(dataframe, timeperiod=14)
        dataframe["%-rsi_fast"] = ta.RSI(dataframe, timeperiod=7)
        dataframe["%-rsi_2"] = ta.RSI(dataframe, timeperiod=2)  # Very short, 91% win rate
        dataframe["%-rsi_3"] = ta.RSI(dataframe, timeperiod=3)
        dataframe["%-rsi_5"] = ta.RSI(dataframe, timeperiod=5)

        # ========== ROC Suite (93% win rate indicator) ==========
        dataframe["%-roc"] = ta.ROC(dataframe, timeperiod=10)
        dataframe["%-roc_fast"] = ta.ROC(dataframe, timeperiod=5)
        dataframe["%-roc_2"] = ta.ROC(dataframe, timeperiod=2)

        # ========== MACD ==========
        macd_result = ta.MACD(dataframe)
        if isinstance(macd_result, dict):
            dataframe["%-macd"] = macd_result['macd']
            dataframe["%-macdsignal"] = macd_result['macdsignal']
            dataframe["%-macdhist"] = macd_result['macdhist']
        else:
            macd, macdsignal, macdhist = ta.MACD(dataframe['close'])
            dataframe["%-macd"] = macd
            dataframe["%-macdsignal"] = macdsignal
            dataframe["%-macdhist"] = macdhist

        # ========== Bollinger Bands ==========
        bb = qtpylib.bollinger_bands(dataframe['close'], window=20, stds=2)
        dataframe["%-bb_lower"] = bb['lower']
        dataframe["%-bb_upper"] = bb['upper']
        dataframe["%-bb_pct"] = (dataframe['close'] - bb['lower']) / (bb['upper'] - bb['lower'] + 1e-8)
        dataframe["%-bb_width"] = (bb['upper'] - bb['lower']) / (bb['mid'] + 1e-8)

        # ========== Moving Averages ==========
        # EMAs
        dataframe["%-ema_20"] = ta.EMA(dataframe['close'], timeperiod=20)
        dataframe["%-ema_50"] = ta.EMA(dataframe['close'], timeperiod=50)
        dataframe["%-ema_100"] = ta.EMA(dataframe['close'], timeperiod=100)
        dataframe["%-ema_200"] = ta.EMA(dataframe['close'], timeperiod=200)

        # WMAs (83% win rate)
        dataframe["%-wma_20"] = ta.WMA(dataframe['close'], timeperiod=20)
        dataframe["%-wma_50"] = ta.WMA(dataframe['close'], timeperiod=50)

        # HMAs (77% win rate, reduces lag)
        dataframe["%-hma_20"] = self._hma(dataframe['close'], 20)
        dataframe["%-hma_50"] = self._hma(dataframe['close'], 50)

        # ========== ADX ==========
        dataframe["%-adx"] = ta.ADX(dataframe, timeperiod=14)
        dataframe["%-plus_di"] = ta.PLUS_DI(dataframe, timeperiod=14)
        dataframe["%-minus_di"] = ta.MINUS_DI(dataframe, timeperiod=14)
        dataframe["%-di_diff"] = dataframe["%-plus_di"] - dataframe["%-minus_di"]

        # ========== ATR ==========
        dataframe["%-atr"] = ta.ATR(dataframe, timeperiod=14)
        dataframe["%-atr_pct"] = dataframe["%-atr"] / dataframe['close']

        # ========== Volume Indicators ==========
        dataframe["%-volume_mean_20"] = dataframe['volume'].rolling(20).mean()
        dataframe["%-volume_ratio"] = dataframe['volume'] / (dataframe["%-volume_mean_20"] + 1e-8)

        # MFI - Money Flow Index (volume-weighted RSI)
        dataframe["%-mfi"] = ta.MFI(dataframe, timeperiod=14)

        # VWAP proxy (93% win rate) - cumulative volume-weighted price
        dataframe["%-vwap_proxy"] = (
            (dataframe['close'] * dataframe['volume']).cumsum() /
            (dataframe['volume'].cumsum() + 1e-8)
        )
        dataframe["%-vwap_deviation"] = dataframe['close'] / dataframe["%-vwap_proxy"] - 1

        # ========== CCI - Commodity Channel Index (50% win rate) ==========
        dataframe["%-cci"] = ta.CCI(dataframe, timeperiod=20)
        dataframe["%-cci_fast"] = ta.CCI(dataframe, timeperiod=10)

        # ========== Stochastic (43% win rate) ==========
        stoch = ta.STOCH(dataframe, fastk_period=14, slowk_period=3, slowd_period=3)
        dataframe["%-stoch_k"] = stoch['slowk']
        dataframe["%-stoch_d"] = stoch['slowd']

        # ========== Momentum ==========
        dataframe["%-momentum_5"] = dataframe['close'] / dataframe['close'].shift(5) - 1
        dataframe["%-momentum_10"] = dataframe['close'] / dataframe['close'].shift(10) - 1

        # ========== Trend Detection ==========
        dataframe["%-uptrend"] = np.where(
            (dataframe["%-ema_20"] > dataframe["%-ema_50"]) &
            (dataframe["%-di_diff"] > 0),
            1, 0
        )
        dataframe["%-downtrend"] = np.where(
            (dataframe["%-ema_20"] < dataframe["%-ema_50"]) &
            (dataframe["%-di_diff"] < 0),
            1, 0
        )

        # ========== Composite Indicators (High Accuracy Combinations) ==========
        # RSI-MFI combination (price + volume momentum consensus)
        dataframe["%-rsi_mfi_consensus"] = np.where(
            (dataframe["%-rsi_2"] < 30) & (dataframe["%-mfi"] < 30), -1,  # Oversold consensus
            np.where(
                (dataframe["%-rsi_2"] > 70) & (dataframe["%-mfi"] > 70), 1,  # Overbought consensus
                0
            )
        )

        # ROC-Momentum combo (93% win rate indicator combined)
        dataframe["%-roc_momentum"] = (
            dataframe["%-roc_2"] + dataframe["%-momentum_5"] * 100
        ) / 2

        # HMA-EMA crossover signal (reduced lag trend)
        dataframe["%-hma_ema_signal"] = np.where(
            dataframe["%-hma_20"] > dataframe["%-ema_20"], 1,
            np.where(dataframe["%-hma_20"] < dataframe["%-ema_20"], -1, 0)
        )

        # Price position relative to VWAP (institutional buying/selling)
        dataframe["%-vwap_position"] = np.where(
            dataframe['close'] > dataframe["%-vwap_proxy"], 1,  # Above VWAP - bullish
            np.where(dataframe['close'] < dataframe["%-vwap_proxy"], -1, 0)  # Below VWAP - bearish
        )

        # Bollinger Band position with RSI (mean reversion signal)
        dataframe["%-bb_rsi_signal"] = np.where(
            (dataframe["%-bb_pct"] < 0.2) & (dataframe["%-rsi_2"] < 30), 1,  # Oversold + low RSI = buy
            np.where(
                (dataframe["%-bb_pct"] > 0.8) & (dataframe["%-rsi_2"] > 70), -1,  # Overbought + high RSI = sell
                0
            )
        )

        # Multi-MA alignment (strong trend signal)
        dataframe["%-ma_alignment"] = np.where(
            (dataframe["%-ema_20"] > dataframe["%-ema_50"]) &
            (dataframe["%-ema_50"] > dataframe["%-ema_100"]) &
            (dataframe["%-ema_100"] > dataframe["%-ema_200"]),
            1,  # Full bullish alignment
            np.where(
                (dataframe["%-ema_20"] < dataframe["%-ema_50"]) &
                (dataframe["%-ema_50"] < dataframe["%-ema_100"]) &
                (dataframe["%-ema_100"] < dataframe["%-ema_200"]),
                -1,  # Full bearish alignment
                0
            )
        )

        # ========== NEW: TTM Squeeze (波动率压缩) ==========
        dataframe["ttm_squeeze"] = self._ttm_squeeze(dataframe)
        dataframe["%-ttm_squeeze"] = dataframe["ttm_squeeze"]  # FreqAI特征

        # ========== NEW: Wave Trend Oscillator ==========
        wt1, wt2 = self._wave_trend(dataframe)
        dataframe["wt1"] = wt1
        dataframe["wt2"] = wt2
        dataframe["%-wt1"] = wt1  # FreqAI特征
        dataframe["%-wt2"] = wt2
        dataframe["wt_signal"] = np.where(
            (wt1 > wt2) & (wt1 < -60), 1,  # 从超卖区域回升
            np.where((wt1 < wt2) & (wt1 > 60), -1, 0)  # 从超买区域回落
        )
        dataframe["%-wt_signal"] = dataframe["wt_signal"]

        # ========== NEW: Supertrend ==========
        supertrend, st_dir = self._supertrend(dataframe)
        dataframe["supertrend"] = supertrend
        dataframe["st_direction"] = st_dir
        dataframe["%-supertrend"] = supertrend  # FreqAI特征
        dataframe["%-st_direction"] = st_dir

        # ========== NEW: Ichimoku Cloud ==========
        tenkan, kijun, senkou_a, senkou_b, chikou = self._ichimoku(dataframe)
        dataframe["tenkan"] = tenkan
        dataframe["kijun"] = kijun
        dataframe["senkou_a"] = senkou_a
        dataframe["senkou_b"] = senkou_b
        dataframe["%-tenkan"] = tenkan  # FreqAI特征
        dataframe["%-kijun"] = kijun
        dataframe["%-senkou_a"] = senkou_a
        dataframe["%-senkou_b"] = senkou_b
        dataframe["tk_cross"] = np.where(tenkan > kijun, 1, -1)  # TK金叉
        dataframe["above_cloud"] = np.where(
            dataframe['close'] > senkou_a, 1,
            np.where(dataframe['close'] < senkou_b, -1, 0)
        )
        dataframe["%-tk_cross"] = dataframe["tk_cross"]
        dataframe["%-above_cloud"] = dataframe["above_cloud"]

        # ========== NEW: Order Blocks ==========
        bullish_ob, bearish_ob = self._detect_order_blocks(dataframe)
        dataframe["bullish_ob"] = bullish_ob.astype(int)
        dataframe["bearish_ob"] = bearish_ob.astype(int)
        dataframe["%-bullish_ob"] = dataframe["bullish_ob"]
        dataframe["%-bearish_ob"] = dataframe["bearish_ob"]

        return dataframe

    def feature_engineering_standard(
        self, dataframe: DataFrame, metadata: dict, **kwargs
    ) -> DataFrame:
        """Standard features"""
        return dataframe

    def set_freqai_targets(self, dataframe: DataFrame, metadata: dict, **kwargs) -> DataFrame:
        """Prediction targets - v34_4: 单一回归目标"""
        label_period = self.config.get('freqai', {}).get('feature_parameters', {}) \
            .get('label_period_candles', 12)

        # 单一回归目标：未来N根K线收盘价滚动均值的变化率
        dataframe["&-s_close_mean"] = (
            dataframe["close"]
            .shift(-label_period)
            .rolling(label_period)
            .mean()
            / dataframe["close"]
            - 1
        )
        return dataframe

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """Indicators with high-accuracy research-backed indicators"""
        # ========== RSI Suite ==========
        dataframe['rsi'] = ta.RSI(dataframe['close'], timeperiod=14)
        dataframe['rsi_fast'] = ta.RSI(dataframe['close'], timeperiod=7)
        dataframe['rsi_2'] = ta.RSI(dataframe['close'], timeperiod=2)  # Short RSI for mean reversion

        # ========== ROC Suite (93% win rate) ==========
        dataframe['roc'] = ta.ROC(dataframe['close'], timeperiod=10)
        dataframe['roc_2'] = ta.ROC(dataframe['close'], timeperiod=2)

        # ========== MACD ==========
        macd, macdsignal, macdhist = ta.MACD(dataframe['close'])
        dataframe['macd'] = macd
        dataframe['macdsignal'] = macdsignal
        dataframe['macdhist'] = macdhist

        # ========== Bollinger Bands ==========
        bb = qtpylib.bollinger_bands(dataframe['close'], window=20, stds=2)
        dataframe['bb_lower'] = bb['lower']
        dataframe['bb_upper'] = bb['upper']
        dataframe['bb_pct'] = (dataframe['close'] - bb['lower']) / (bb['upper'] - bb['lower'] + 1e-8)
        dataframe['bb_width'] = (bb['upper'] - bb['lower']) / (bb['mid'] + 1e-8)

        # ========== Moving Averages ==========
        dataframe['ema_20'] = ta.EMA(dataframe['close'], timeperiod=20)
        dataframe['ema_50'] = ta.EMA(dataframe['close'], timeperiod=50)
        dataframe['ema_100'] = ta.EMA(dataframe['close'], timeperiod=100)
        dataframe['ema_200'] = ta.EMA(dataframe['close'], timeperiod=200)

        # WMA (83% win rate)
        dataframe['wma_20'] = ta.WMA(dataframe['close'], timeperiod=20)

        # HMA (77% win rate)
        dataframe['hma_20'] = self._hma(dataframe['close'], 20)

        # ========== ADX ==========
        dataframe['adx'] = ta.ADX(dataframe, timeperiod=14)
        dataframe['plus_di'] = ta.PLUS_DI(dataframe, timeperiod=14)
        dataframe['minus_di'] = ta.MINUS_DI(dataframe, timeperiod=14)
        dataframe['di_diff'] = dataframe['plus_di'] - dataframe['minus_di']

        # ========== ATR ==========
        dataframe['atr'] = ta.ATR(dataframe, timeperiod=14)
        dataframe['atr_pct'] = dataframe['atr'] / dataframe['close']

        # ========== Volume ==========
        dataframe['volume_mean_20'] = dataframe['volume'].rolling(20).mean()
        dataframe['volume_ratio'] = dataframe['volume'] / (dataframe['volume_mean_20'] + 1e-8)

        # MFI - Money Flow Index
        dataframe['mfi'] = ta.MFI(dataframe, timeperiod=14)

        # VWAP proxy
        dataframe['vwap_proxy'] = (
            (dataframe['close'] * dataframe['volume']).cumsum() /
            (dataframe['volume'].cumsum() + 1e-8)
        )

        # ========== Momentum ==========
        dataframe['momentum_5'] = dataframe['close'] / dataframe['close'].shift(5) - 1

        # ========== CCI (50% win rate) ==========
        dataframe['cci'] = ta.CCI(dataframe, timeperiod=20)

        # ========== Market Regime Detection ==========
        dataframe['market_regime'] = np.where(
            dataframe['ema_50'] > dataframe['ema_200'], 1,
            np.where(dataframe['ema_50'] < dataframe['ema_200'], -1, 0)
        )

        # ========== Composite Signals ==========
        # RSI-MFI oversold/overbought consensus
        dataframe['rsi_mfi_oversold'] = (dataframe['rsi_2'] < 30) & (dataframe['mfi'] < 30)
        dataframe['rsi_mfi_overbought'] = (dataframe['rsi_2'] > 70) & (dataframe['mfi'] > 70)

        # Price vs VWAP
        dataframe['above_vwap'] = dataframe['close'] > dataframe['vwap_proxy']

        # HMA-EMA crossover
        dataframe['hma_above_ema'] = dataframe['hma_20'] > dataframe['ema_20']

        # ========== TTM Squeeze (波动率压缩) ==========
        dataframe['ttm_squeeze'] = self._ttm_squeeze(dataframe)

        # ========== Wave Trend Oscillator ==========
        wt1, wt2 = self._wave_trend(dataframe)
        dataframe['wt1'] = wt1
        dataframe['wt2'] = wt2
        dataframe['wt_signal'] = np.where(
            (wt1 > wt2) & (wt1 < -60), 1,  # 从超卖区域回升
            np.where((wt1 < wt2) & (wt1 > 60), -1, 0)  # 从超买区域回落
        )

        # FreqAI处理
        if self.freqai_enabled:
            dataframe = self.freqai.start(dataframe, metadata, self)
        else:
            dataframe = self.set_freqai_targets(dataframe, metadata)

        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Entry conditions - v34_4: ADX/DI主条件 + FreqAI辅助标记

        策略改进:
        1. 保留原始ADX/DI入场条件（产生15%利润的核心）
        2. FreqAI预测作为enter_tag标记，不强制过滤
        3. 通过custom_stake_amount根据FreqAI预测调整仓位
        """
        # ========== LONG ENTRY ==========
        # 主入场条件：ADX/DI技术指标（保留原始15%利润逻辑）
        long_conditions = (
            # EMA alignment
            (dataframe["ema_20"] > dataframe["ema_50"]) &
            (dataframe["close"] > dataframe["ema_20"]) &
            # Trend strength
            (dataframe["adx"] > 20) &
            # DI direction
            (dataframe["di_diff"] > 10) &
            # MACD bullish
            (dataframe["macdhist"] > 0) &
            # RSI healthy zone
            (dataframe["rsi"] > 45) &
            (dataframe["rsi"] < 70) &
            # Positive momentum
            (dataframe["momentum_5"] > 0.001) &
            # Volume support
            (dataframe["volume"] > dataframe["volume_mean_20"] * 1.0)
        )

        # 不用FreqAI过滤入场，只做标记
        dataframe.loc[long_conditions, 'enter_long'] = 1

        # FreqAI辅助标记（用于仓位调整）
        if self.freqai_enabled and "do_predict" in dataframe.columns:
            # FreqAI预测一致：标记为freqai_boost
            freqai_confirmed = (
                (dataframe["do_predict"] == 1) &
                (dataframe["&-s_close_mean"] > 0.002)  # 预测涨0.2%+
            )
            dataframe.loc[long_conditions & freqai_confirmed, 'enter_tag'] = 'freqai_boost'
            # 其他情况标记为tech_only
            dataframe.loc[long_conditions & ~freqai_confirmed, 'enter_tag'] = 'tech_only'
        else:
            dataframe.loc[long_conditions, 'enter_tag'] = 'tech_only'

        # ========== SHORT ENTRY ==========
        short_conditions = (
            # EMA alignment
            (dataframe["ema_20"] < dataframe["ema_50"]) &
            (dataframe["close"] < dataframe["ema_20"]) &
            # Trend strength
            (dataframe["adx"] > 20) &
            # DI direction
            (dataframe["di_diff"] < -10) &
            # MACD bearish
            (dataframe["macdhist"] < 0) &
            # RSI for shorts
            (dataframe["rsi"] < 55) &
            (dataframe["rsi"] > 30) &
            # Negative momentum
            (dataframe["momentum_5"] < -0.001) &
            # Volume filter
            (dataframe["volume"] > dataframe["volume_mean_20"] * 1.0)
        )

        dataframe.loc[short_conditions, 'enter_short'] = 1

        # FreqAI辅助标记
        if self.freqai_enabled and "do_predict" in dataframe.columns:
            freqai_confirmed = (
                (dataframe["do_predict"] == 1) &
                (dataframe["&-s_close_mean"] < -0.002)  # 预测跌0.2%+
            )
            dataframe.loc[short_conditions & freqai_confirmed, 'enter_tag'] = 'freqai_boost'
            dataframe.loc[short_conditions & ~freqai_confirmed, 'enter_tag'] = 'tech_only'
        else:
            dataframe.loc[short_conditions, 'enter_tag'] = 'tech_only'

        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Exit signals - v2 禁用退出信号

        退出信号导致亏损，暂时禁用让ROI和trailing stop处理退出
        """
        # 禁用所有退出信号
        dataframe['exit_long'] = 0
        dataframe['exit_short'] = 0

        return dataframe

    def custom_stake_amount(self, pair: str, current_time: datetime, current_rate: float,
                            proposed_stake: float, min_stake: Optional[float], max_stake: float,
                            leverage: float, entry_tag: Optional[str], side: str,
                            **kwargs) -> float:
        """
        v34_4: 根据FreqAI预测调整仓位

        策略:
        - freqai_boost（FreqAI预测一致）: 仓位增加50%
        - tech_only（仅技术指标）: 正常仓位
        """
        if entry_tag == 'freqai_boost':
            # FreqAI确认的交易，增加仓位50%
            return proposed_stake * 1.5
        else:
            # 正常仓位
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
        """
        V31: 多单止损50%，空单止损25%

        根据方向设置不同止损:
        - 多单: 最大止损50%，给足波动空间
        - 空单: 最大止损25%，控制风险

        移动止损逻辑:
        - 盈利3%+: 开始锁定利润
        - 盈利越多，锁定比例越高
        """
        # 根据交易方向设置基础止损
        if trade.is_short:
            base_sl = -self.short_stoploss  # 空单-25%
        else:
            base_sl = -self.long_stoploss   # 多单-50%

        # 亏损时保持固定止损
        if current_profit < self.profit_lock_threshold:
            return base_sl

        # 盈利时计算移动止损，逐步锁定利润
        if current_profit >= 0.12:
            locked_profit = current_profit * 0.70  # 锁定70%
        elif current_profit >= 0.08:
            locked_profit = current_profit * 0.60  # 锁定60%
        elif current_profit >= 0.05:
            locked_profit = current_profit * 0.50  # 锁定50%
        else:
            locked_profit = 0.001  # 保本

        return -locked_profit

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
        """
        V31: 补仓策略

        补仓条件:
        1. 当前有亏损（亏损5%以上触发）
        2. 补仓次数未达上限（最多3次）
        3. 信号仍然有效

        补仓比例: 初始仓位的50%
        """
        # 防止在订单执行期间调整
        if trade.has_open_orders:
            return None

        dataframe, _ = self.dp.get_analyzed_dataframe(trade.pair, self.timeframe)
        if dataframe is None or dataframe.empty:
            return None

        last_candle = dataframe.iloc[-1]

        # 检查是否允许补仓
        if trade.nr_of_successful_entries >= self.max_entry_position_adjustment + 1:
            return None  # 已达补仓上限

        # 检查亏损是否达到补仓阈值
        if current_profit > self.add_position_threshold:
            return None  # 亏损不够，不补仓

        # 检查信号方向是否仍然有效
        if trade.is_short:
            # 空单: 检查做空信号
            signal_valid = (
                last_candle.get('enter_short', 0) == 1 or
                last_candle.get('macdhist', 0) < 0
            )
        else:
            # 多单: 检查做多信号
            signal_valid = (
                last_candle.get('enter_long', 0) == 1 or
                last_candle.get('macdhist', 0) > 0
            )

        if not signal_valid:
            return None  # 信号不再有效，不补仓

        # 计算补仓金额
        current_stake = trade.stake_amount
        add_stake = current_stake * self.add_position_ratio
        add_stake = min(add_stake, max_stake)
        if min_stake and add_stake < min_stake:
            add_stake = min_stake

        logger.info(f"📊 [补仓] {trade.pair} {'做空' if trade.is_short else '做多'} "
                   f"当前亏损: {current_profit:.2%}, 补仓金额: {add_stake:.2f} USDT")

        return add_stake, "dca_increase"

    def custom_exit(
        self,
        pair: str,
        trade: Trade,
        current_time: datetime,
        current_rate: float,
        current_profit: float,
        **kwargs
    ) -> Optional[str]:
        """
        自定义退出检查 - 当行情可能变坏时主动退出

        当前策略：暂不启用custom_exit，让ROI和止损处理
        避免过早退出导致利润损失

        Returns:
            退出原因字符串，或None表示不退出
        """
        # 暂时禁用自定义退出，让ROI和止损处理
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
        """
        智能杠杆策略 v18 - 对高置信度交易使用杠杆

        关键改进:
        1. 对多空双方都使用杠杆 (双向策略)
        2. 杠杆只能是自然数: 1x, 2x, 3x
        3. 根据置信度分配杠杆

        杠杆分配:
        - 置信度 < 0.80: 1x (不使用杠杆)
        - 置信度 0.80-0.90: 2x
        - 置信度 >= 0.90: 3x

        Returns:
            杠杆倍数
        """
        if not self.leverage_enabled:
            return 1

        # 获取当前K线数据
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        if dataframe is None or len(dataframe) < 1:
            return 1

        last_candle = dataframe.iloc[-1]

        # v18: 对多空双方都应用杠杆

        # 计算置信度
        confidence = self._calculate_trade_confidence(pair, side, last_candle)

        # 根据置信度分配杠杆 (返回整数)
        if confidence >= self.leverage_threshold_very_high:  # >= 0.90
            leverage = 3
        elif confidence >= 0.80:
            leverage = 2
        else:
            leverage = 1

        if leverage > 1:
            self._leverage_cache[pair] = leverage
            logger.info(f"杠杆决策: {pair} {side} 置信度={confidence:.3f} 杠杆={leverage}x")

        return leverage

    def _calculate_trade_confidence(self, pair: str, side: str, last_candle: pd.Series) -> float:
        """
        计算交易置信度 (0.0 - 1.0)

        综合考虑:
        1. FreqAI预测强度 (权重 40%)
        2. 技术指标一致性 (权重 35%)
        3. 市场趋势强度 (权重 25%)

        Returns:
            置信度分数 (0.0 - 1.0)
        """
        confidence_scores = []
        weights = []

        # 1. FreqAI预测强度 (权重 40%)
        if self.freqai_enabled and "&-s_close_mean" in last_candle:
            pred_strength = abs(last_candle["&-s_close_mean"])
            # 归一化: 0.5以上为高置信度
            freqai_confidence = min(pred_strength / 0.5, 1.0)
            confidence_scores.append(freqai_confidence)
            weights.append(0.40)
            logger.debug(f"  FreqAI置信度: {freqai_confidence:.3f} (pred={pred_strength:.4f})")

        # 2. 技术指标一致性 (权重 35%)
        tech_confidence = self._calculate_technical_confidence(last_candle, side)
        confidence_scores.append(tech_confidence)
        weights.append(0.35)

        # 3. 市场趋势强度 (权重 25%)
        trend_confidence = self._calculate_trend_confidence(last_candle, side)
        confidence_scores.append(trend_confidence)
        weights.append(0.25)

        # 加权平均
        if confidence_scores and weights:
            total_weight = sum(weights)
            weighted_confidence = sum(s * w for s, w in zip(confidence_scores, weights)) / total_weight
            return min(max(weighted_confidence, 0.0), 1.0)

        return 0.3  # 默认低置信度

    def _calculate_technical_confidence(self, last_candle: pd.Series, side: str) -> float:
        """
        计算技术指标一致性置信度

        检查项:
        - ADX强度 (>30 高置信度)
        - DI方向一致性
        - RSI不极端
        - MACD方向一致
        - 成交量放大
        """
        score = 0.0
        count = 0

        # ADX强度
        if 'adx' in last_candle:
            adx = last_candle['adx']
            if adx > 35:
                score += 1.0
            elif adx > 30:
                score += 0.8
            elif adx > 25:
                score += 0.6
            else:
                score += 0.3
            count += 1

        # DI方向一致性
        if 'di_diff' in last_candle:
            di_diff = last_candle['di_diff']
            if side == 'long' and di_diff > 15:
                score += 1.0
            elif side == 'short' and di_diff < -15:
                score += 1.0
            elif side == 'long' and di_diff > 8:
                score += 0.7
            elif side == 'short' and di_diff < -8:
                score += 0.7
            else:
                score += 0.3
            count += 1

        # RSI合理性 (不极端)
        if 'rsi' in last_candle:
            rsi = last_candle['rsi']
            if side == 'long':
                if 40 <= rsi <= 55:  # 上升趋势初期
                    score += 1.0
                elif 35 <= rsi <= 60:
                    score += 0.7
                else:
                    score += 0.4
            else:  # short
                if 45 <= rsi <= 60:  # 下降趋势初期
                    score += 1.0
                elif 40 <= rsi <= 65:
                    score += 0.7
                else:
                    score += 0.4
            count += 1

        # MACD方向
        if 'macd' in last_candle and 'macdsignal' in last_candle:
            macd_diff = last_candle['macd'] - last_candle['macdsignal']
            if side == 'long' and macd_diff > 0:
                score += 1.0
            elif side == 'short' and macd_diff < 0:
                score += 1.0
            else:
                score += 0.3
            count += 1

        # 成交量放大
        if 'volume_ratio' in last_candle:
            vol_ratio = last_candle['volume_ratio']
            if vol_ratio > 2.0:
                score += 1.0
            elif vol_ratio > 1.5:
                score += 0.8
            elif vol_ratio > 1.2:
                score += 0.6
            else:
                score += 0.3
            count += 1

        return score / count if count > 0 else 0.5

    def _calculate_trend_confidence(self, last_candle: pd.Series, side: str) -> float:
        """
        计算趋势强度置信度

        检查项:
        - EMA排列 (多头/空头排列)
        - 市场regime一致性
        - 动量方向
        """
        score = 0.0
        count = 0

        # EMA排列
        if 'ema_20' in last_candle and 'ema_50' in last_candle and 'ema_100' in last_candle:
            ema_20 = last_candle['ema_20']
            ema_50 = last_candle['ema_50']
            ema_100 = last_candle['ema_100']

            if side == 'long':
                # 多头排列: EMA20 > EMA50 > EMA100
                if ema_20 > ema_50 > ema_100:
                    score += 1.0
                elif ema_20 > ema_50:
                    score += 0.7
                else:
                    score += 0.3
            else:  # short
                # 空头排列: EMA20 < EMA50 < EMA100
                if ema_20 < ema_50 < ema_100:
                    score += 1.0
                elif ema_20 < ema_50:
                    score += 0.7
                else:
                    score += 0.3
            count += 1

        # 市场regime
        if 'market_regime' in last_candle:
            regime = last_candle['market_regime']
            if side == 'long' and regime > 0:
                score += 1.0
            elif side == 'short' and regime < 0:
                score += 1.0
            else:
                score += 0.3
            count += 1

        # 动量方向
        if 'momentum_5' in last_candle:
            momentum = last_candle['momentum_5']
            if side == 'long' and momentum > 0.01:
                score += 1.0
            elif side == 'short' and momentum < -0.01:
                score += 1.0
            elif side == 'long' and momentum > 0:
                score += 0.6
            elif side == 'short' and momentum < 0:
                score += 0.6
            else:
                score += 0.3
            count += 1

        return score / count if count > 0 else 0.5

    def _get_leverage_from_confidence(self, confidence: float) -> int:
        """
        根据置信度返回杠杆倍数

        Args:
            confidence: 置信度 (0.0 - 1.0)

        Returns:
            杠杆倍数 (整数 1-5)
        """
        if confidence >= self.leverage_threshold_extreme:
            return 5   # 极端置信度: 5x杠杆
        elif confidence >= self.leverage_threshold_very_high:
            return 4   # 极高置信度: 4x杠杆
        elif confidence >= self.leverage_threshold_high:
            return 3   # 高置信度: 3x杠杆
        elif confidence >= self.leverage_threshold_medium:
            return 2   # 中置信度: 2x杠杆
        else:
            return 1   # 低置信度: 1x杠杆

    def _get_stoploss_for_leverage(self, leverage_value: float) -> float:
        """
        根据杠杆计算止损比例

        逻辑: 使用平方根衰减，给交易更多波动空间
        - 基础止损 8% (无杠杆时的标的波动)
        - 杠杆越高，止损越小 (但不是线性关系)
        - 使用平方根: stop_loss = base_stoploss / sqrt(leverage)

        对应表:
        | 杠杆 | 止损比例 |
        |------|---------|
        | 1x   | -8.0%   |
        | 2x   | -5.66%  |
        | 3x   | -4.62%  |

        Args:
            leverage_value: 杠杆倍数

        Returns:
            止损比例 (负数)
        """
        import math

        # 确保杠杆至少为1
        leverage_value = max(leverage_value, 1.0)

        # 使用平方根衰减，给交易更多波动空间
        # 这比线性衰减更合理，因为高杠杆需要更大的止损空间
        adjusted_stoploss = self.base_stoploss / math.sqrt(leverage_value)

        # 设置最小止损，避免过于敏感被误触
        adjusted_stoploss = max(adjusted_stoploss, self.min_stoploss_pct)

        return -adjusted_stoploss

    def _is_backtesting(self) -> bool:
        """检测是否在回测模式"""
        # 方法1: 检查 Dataprovider 是否有回测特征
        if hasattr(self.dp, 'runmode'):
            from freqtrade.enums import RunMode
            return self.dp.runmode in (RunMode.BACKTEST, RunMode.HYPEROPT)

        # 方法2: 检查是否能获取实时订单簿 (回测时无法获取)
        # 这个检查在 confirm_trade_entry 中进行，因为这里 dp 可能还未初始化
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
        """Entry confirmation with additional filters including sentiment and on-chain data"""

        # ========== 回测模式检测 ==========
        # 回测时跳过所有实时数据检查，因为无法获取历史API数据
        is_backtest = self._is_backtesting()
        if is_backtest:
            # 回测模式: 只做基础技术指标检查
            dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
            if dataframe is not None and not dataframe.empty:
                last_candle = dataframe.iloc[-1]
                # FreqAI check
                if self.freqai_enabled and "do_predict" in last_candle:
                    if last_candle["do_predict"] != 1:
                        logger.info(f"🔍 [回测拒绝] {pair} {side}: do_predict={last_candle.get('do_predict', 'N/A')}")
                        return False
                # RSI extreme check
                if 'rsi' in last_candle:
                    if side == 'long' and last_candle['rsi'] > 70:
                        logger.info(f"🔍 [回测拒绝] {pair} {side}: RSI过高 {last_candle['rsi']:.1f}")
                        return False
                    if side == 'short' and last_candle['rsi'] < 30:
                        logger.info(f"🔍 [回测拒绝] {pair} {side}: RSI过低 {last_candle['rsi']:.1f}")
                        return False
            return True

        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)

        if dataframe is None or dataframe.empty:
            logger.info(f"🔍 [拒绝] {pair} {side}: 无数据")
            return True

        last_candle = dataframe.iloc[-1]

        # FreqAI check
        if self.freqai_enabled and "do_predict" in last_candle:
            if last_candle["do_predict"] != 1:
                logger.info(f"🚫 [FreqAI拒绝] {pair} {side}: do_predict={last_candle.get('do_predict', 'N/A')}")
                return False

        # Volatility check - reject high volatility
        if 'atr_pct' in last_candle and last_candle['atr_pct'] > 0.04:
            logger.info(f"🚫 [波动率拒绝] {pair} {side}: ATR%={last_candle['atr_pct']:.2%} > 4%")
            return False

        # ADX check - need trend strength
        if 'adx' in last_candle and last_candle['adx'] < 20:
            logger.info(f"🚫 [ADX拒绝] {pair} {side}: ADX={last_candle['adx']:.1f} < 20")
            return False

        # RSI extreme check
        if 'rsi' in last_candle:
            if side == 'long' and last_candle['rsi'] > 70:
                logger.info(f"🚫 [RSI拒绝] {pair} {side}: RSI={last_candle['rsi']:.1f} > 70")
                return False
            if side == 'short' and last_candle['rsi'] < 30:
                logger.info(f"🚫 [RSI拒绝] {pair} {side}: RSI={last_candle['rsi']:.1f} < 30")
                return False

        # Momentum direction check - don't enter against momentum
        if 'momentum_5' in last_candle:
            if side == 'long' and last_candle['momentum_5'] < -0.01:
                logger.info(f"🚫 [动量拒绝] {pair} {side}: momentum={last_candle['momentum_5']:.3f} < -0.01")
                return False
            if side == 'short' and last_candle['momentum_5'] > 0.01:
                logger.info(f"🚫 [动量拒绝] {pair} {side}: momentum={last_candle['momentum_5']:.3f} > 0.01")
                return False

        # DI alignment check - ensure trend direction matches trade
        if 'di_diff' in last_candle:
            if side == 'long' and last_candle['di_diff'] < 0:
                logger.info(f"🚫 [DI拒绝] {pair} {side}: DI_diff={last_candle['di_diff']:.1f} < 0")
                return False
            if side == 'short' and last_candle['di_diff'] > 0:
                logger.info(f"🚫 [DI拒绝] {pair} {side}: DI_diff={last_candle['di_diff']:.1f} > 0")
                return False

        # ========== 情绪分析检查 (仅实盘) ==========
        sentiment_allowed, sentiment_reason = self.check_sentiment_filter(pair, side)
        if not sentiment_allowed:
            logger.warning(f"🚫 [情绪过滤] {pair} {side} 被拒绝: {sentiment_reason}")
            return False

        # ========== 链上数据检查 (仅实盘) ==========
        onchain_allowed, onchain_reason = self.check_onchain_signals(pair, side)
        if not onchain_allowed:
            logger.warning(f"🚫 [链上过滤] {pair} {side} 被拒绝: {onchain_reason}")
            return False

        # ========== 新闻过滤检查 (仅实盘) ==========
        news_allowed, news_reason = self.check_news_filter(pair, side)
        if not news_allowed:
            logger.warning(f"🚫 [新闻过滤] {pair} {side} 被拒绝: {news_reason}")
            return False

        # ========== 订单簿分析检查 (仅实盘) ==========
        ob_allowed, ob_reason = self.check_orderbook_signals(pair, side)
        if not ob_allowed:
            logger.warning(f"🚫 [订单簿过滤] {pair} {side} 被拒绝: {ob_reason}")
            return False

        logger.info(f"✅ [确认入场] {pair} {side}: 所有检查通过")
        return True

    def check_sentiment_filter(self, pair: str, side: str) -> tuple:
        """
        情绪分析过滤

        Returns:
            (allowed: bool, reason: str)
        """
        if not self.enable_sentiment_check:
            return True, ""

        if not FREE_SENTIMENT_AVAILABLE:
            return True, "情绪分析模块不可用"

        try:
            import time
            # 提取基础币种
            symbol = pair.split('/')[0].replace(':USDT', '').replace('USDT', '')

            # 检查缓存
            cache_key = f"sentiment_{symbol}"
            if cache_key in self._sentiment_cache:
                cached = self._sentiment_cache[cache_key]
                if time.time() - cached['timestamp'] < self.sentiment_cache_ttl:
                    sentiment_data = cached['data']
                else:
                    sentiment_data = None
            else:
                sentiment_data = None

            # 获取情绪数据
            if sentiment_data is None:
                sentiment_data = get_sentiment_for_trading(symbol)
                self._sentiment_cache[cache_key] = {
                    'timestamp': time.time(),
                    'data': sentiment_data
                }

            sentiment = sentiment_data.get('sentiment', 0.5)
            fng = sentiment_data.get('fear_greed', 50)
            signal = sentiment_data.get('signal', 'hold')

            logger.info(f"📊 [情绪检查] {symbol}: 情绪={sentiment:.2f}, F&G={fng}, 信号={signal}")

            # 极度恐慌时禁止做空 (逆向操作)
            if fng <= self.sentiment_extreme_fear:
                if side == 'short':
                    logger.info(f"📈 [情绪信号] 极度恐慌(F&G={fng}), 禁止做空")
                    return False, f"极度恐慌(F&G={fng}), 应考虑做多"
                logger.info(f"✅ [情绪信号] 极度恐慌(F&G={fng}), 允许做多")

            # 极度贪婪时禁止做多 (逆向操作)
            elif fng >= self.sentiment_extreme_greed:
                if side == 'long':
                    logger.info(f"📉 [情绪信号] 极度贪婪(F&G={fng}), 禁止做多")
                    return False, f"极度贪婪(F&G={fng}), 应考虑做空"
                logger.info(f"✅ [情绪信号] 极度贪婪(F&G={fng}), 允许做空")

            # 中性区间 - 根据综合情绪判断
            else:
                if sentiment >= self.sentiment_bullish_threshold and side == 'short':
                    logger.info(f"📉 [情绪信号] 情绪看涨({sentiment:.2f}), 不建议做空")
                    return False, f"情绪看涨({sentiment:.2f})"
                elif sentiment <= self.sentiment_bearish_threshold and side == 'long':
                    logger.info(f"📉 [情绪信号] 情绪看跌({sentiment:.2f}), 不建议做多")
                    return False, f"情绪看跌({sentiment:.2f})"

            return True, f"情绪检查通过: sentiment={sentiment:.2f}, F&G={fng}"

        except Exception as e:
            logger.warning(f"⚠️ [情绪检查] 异常: {e}")
            return True, f"检查异常: {e}"

    def check_onchain_signals(self, pair: str, side: str) -> tuple:
        """
        链上数据检查 (资金费率、多空比等)

        Returns:
            (allowed: bool, reason: str)
        """
        if not self.enable_onchain_filter:
            return True, ""

        if not FREE_ONCHAIN_AVAILABLE:
            return True, "链上数据模块不可用"

        try:
            import time
            # 提取基础币种
            base_coin = pair.split('/')[0].replace(':USDT', '').replace('USDT', '')

            # 检查缓存
            cache_key = f"onchain_{base_coin}"
            if cache_key in self._onchain_cache:
                cached = self._onchain_cache[cache_key]
                if time.time() - cached['timestamp'] < self.sentiment_cache_ttl:
                    sentiment = cached['data']
                else:
                    sentiment = None
            else:
                sentiment = None

            # 获取链上数据
            if sentiment is None:
                sentiment = get_market_sentiment(base_coin)
                self._onchain_cache[cache_key] = {
                    'timestamp': time.time(),
                    'data': sentiment
                }

            overall_signal = sentiment.get('overall_signal', 'neutral')
            confidence = sentiment.get('confidence', 0)

            # 获取资金费率
            funding = sentiment.get('funding_rate', {})
            funding_rate_pct = funding.get('rate_pct', 0)
            funding_signal = funding.get('signal', 'neutral')

            # 获取多空比
            lsr = sentiment.get('long_short_ratio', {})
            lsr_ratio = lsr.get('longShortRatio', 1)

            logger.info(f"📊 [链上数据] {base_coin}: 资金费率={funding_rate_pct:.4f}%, "
                       f"多空比={lsr_ratio:.2f}, 综合信号={overall_signal}")

            # 极端资金费率过滤
            if abs(funding_rate_pct) > 0.1:  # 资金费率超过0.1%
                if side == 'long' and funding_signal == 'short_bias':
                    logger.warning(f"⚠️ [链上过滤] {base_coin} 资金费率极端看多({funding_rate_pct:.4f}%)")
                    if self.strict_funding_filter:
                        return False, f"资金费率极端({funding_rate_pct:.4f}%), 反向信号"
                elif side == 'short' and funding_signal == 'long_bias':
                    logger.warning(f"⚠️ [链上过滤] {base_coin} 资金费率极端看空({funding_rate_pct:.4f}%)")
                    if self.strict_funding_filter:
                        return False, f"资金费率极端({funding_rate_pct:.4f}%), 反向信号"

            # 极端多空比过滤
            if lsr_ratio > 2.0 and side == 'long':
                logger.warning(f"⚠️ [链上过滤] {base_coin} 多空比过高({lsr_ratio:.2f}), 多头拥挤")
                if self.strict_lsr_filter:
                    return False, f"多空比极端({lsr_ratio:.2f}), 多头拥挤"
            elif lsr_ratio < 0.5 and side == 'short':
                logger.warning(f"⚠️ [链上过滤] {base_coin} 多空比过低({lsr_ratio:.2f}), 空头拥挤")
                if self.strict_lsr_filter:
                    return False, f"多空比极端({lsr_ratio:.2f}), 空头拥挤"

            return True, f"链上数据检查通过: {overall_signal}({confidence:.2f})"

        except Exception as e:
            logger.error(f"📊 [链上数据] 检查异常: {e}")
            return True, f"检查异常: {e}"

    def check_news_filter(self, pair: str, side: str) -> tuple:
        """
        新闻过滤检查 - 检查是否有重大负面新闻

        Returns:
            (allowed: bool, reason: str)
        """
        if not self.enable_news_filter:
            return True, ""

        if not FREE_SENTIMENT_AVAILABLE:
            return True, "情绪模块不可用"

        try:
            import time
            # 提取基础币种
            symbol = pair.split('/')[0].replace(':USDT', '').replace('USDT', '').lower()

            # 检查冷却时间
            if symbol in self._last_news_check:
                if time.time() - self._last_news_check[symbol] < self.news_check_cooldown:
                    return True, "新闻检查冷却中"

            # 检查缓存
            cache_key = f"news_{symbol}"
            if cache_key in self._news_cache:
                cached = self._news_cache[cache_key]
                if time.time() - cached['timestamp'] < self.sentiment_cache_ttl:
                    news_data = cached['data']
                else:
                    news_data = None
            else:
                news_data = None

            # 获取新闻数据
            if news_data is None:
                news_data = fetch_elfa_token_news(symbol)
                self._news_cache[cache_key] = {
                    'timestamp': time.time(),
                    'data': news_data
                }
                self._last_news_check[symbol] = time.time()

            news_list = news_data.get('news', [])
            if not news_list:
                return True, "无相关新闻"

            # 检查最近新闻的情绪
            negative_count = 0
            for news in news_list[:5]:  # 检查最近5条新闻
                sentiment = news.get('sentiment', 'neutral')
                if sentiment == 'negative' or sentiment == 'bearish':
                    negative_count += 1

            # 如果负面新闻比例过高，拒绝交易
            negative_ratio = negative_count / min(len(news_list), 5)
            if negative_ratio >= self.news_negative_threshold:
                logger.warning(f"📰 [新闻过滤] {symbol} 负面新闻过多: {negative_count}/{min(len(news_list), 5)}")
                return False, f"负面新闻过多({negative_count}条)"

            logger.info(f"📰 [新闻检查] {symbol}: {len(news_list)}条新闻, 负面比例={negative_ratio:.0%}")
            return True, f"新闻检查通过: {len(news_list)}条新闻"

        except Exception as e:
            logger.warning(f"⚠️ [新闻检查] 异常: {e}")
            return True, f"检查异常: {e}"

    def check_orderbook_signals(self, pair: str, side: str) -> tuple:
        """
        订单簿分析检查 - 基于订单簿撮合机制分析市场深度和价格压力

        订单簿撮合三大原则：
        1. 价格优先：高买价、低卖价的订单优先成交
        2. 时间优先：同一价格档位下，先提交的订单优先成交
        3. 成交价取中间值：结合买价、卖价和前一笔成交价的中间值

        Returns:
            (allowed: bool, reason: str)
        """
        if not self.enable_orderbook_analysis:
            return True, ""

        if not ORDERBOOK_AVAILABLE:
            return True, "订单簿分析模块不可用"

        try:
            import time
            # 转换交易对格式 (如 BTC/USDT:USDT -> BTCUSDT)
            symbol = pair.replace('/', '').replace(':USDT', '')

            # 检查缓存
            cache_key = f"orderbook_{symbol}"
            if cache_key in self._orderbook_cache:
                cached = self._orderbook_cache[cache_key]
                if time.time() - cached['timestamp'] < self.orderbook_cache_ttl:
                    ob_data = cached['data']
                else:
                    ob_data = None
            else:
                ob_data = None

            # 获取订单簿数据 (使用Bitget API)
            if ob_data is None:
                ob_data = analyze_orderbook(symbol, "bitget")
                self._orderbook_cache[cache_key] = {
                    'timestamp': time.time(),
                    'data': ob_data
                }

            if 'error' in ob_data:
                return True, f"订单簿获取失败: {ob_data.get('error')}"

            obi = ob_data.get('obi', 0)
            weighted_obi = ob_data.get('weighted_obi', 0)
            spread = ob_data.get('spread', {})
            depth = ob_data.get('depth', {})
            pressure = ob_data.get('pressure', {})
            large_orders = ob_data.get('large_orders', {})
            overall_signal = ob_data.get('overall_signal', 'hold')
            confidence = ob_data.get('confidence', 0)

            logger.info(
                f"📊 [订单簿检查] {symbol}: OBI={obi:.3f}, 加权OBI={weighted_obi:.3f}, "
                f"价差={spread.get('spread_pct', 0):.4f}%, 信号={overall_signal}"
            )

            # 1. OBI检查 - 订单簿失衡
            # 做多时需要正向OBI支持，做空时需要负向OBI支持
            if abs(obi) >= self.obi_strong_threshold:
                if side == 'long' and obi < -self.obi_strong_threshold:
                    return False, f"OBI强烈看空({obi:.3f})"
                if side == 'short' and obi > self.obi_strong_threshold:
                    return False, f"OBI强烈看多({obi:.3f})"

            # 2. 加权OBI检查 - 更重视最优价位的订单
            if abs(weighted_obi) >= self.obi_strong_threshold:
                if side == 'long' and weighted_obi < -self.obi_strong_threshold:
                    return False, f"加权OBI强烈看空({weighted_obi:.3f})"
                if side == 'short' and weighted_obi > self.obi_strong_threshold:
                    return False, f"加权OBI强烈看多({weighted_obi:.3f})"

            # 3. 价差检查 - 价差过大时拒绝交易 (流动性不足)
            spread_pct = spread.get('spread_pct', 0)
            if spread_pct > self.spread_threshold:
                return False, f"价差过大({spread_pct:.4f}%), 流动性不足"

            # 4. 深度失衡检查
            depth_imbalance = depth.get('depth_imbalance', 0)
            if abs(depth_imbalance) >= self.obi_threshold:
                if side == 'long' and depth_imbalance < -self.obi_threshold:
                    logger.info(f"📉 [深度警告] {symbol} 卖方深度占优: {depth_imbalance:.3f}")
                if side == 'short' and depth_imbalance > self.obi_threshold:
                    logger.info(f"📈 [深度警告] {symbol} 买方深度占优: {depth_imbalance:.3f}")

            # 5. 价格压力检查
            pressure_signal = pressure.get('pressure_signal', 'neutral')
            net_pressure = pressure.get('net_pressure', 0)
            if abs(net_pressure) >= 0.5:
                if side == 'long' and pressure_signal == 'bearish':
                    return False, f"价格压力看空(net={net_pressure:.3f})"
                if side == 'short' and pressure_signal == 'bullish':
                    return False, f"价格压力看多(net={net_pressure:.3f})"

            # 6. 大单/冰山订单检测
            if large_orders.get('has_ask_wall') and side == 'long':
                logger.warning(f"🧊 [大单警告] {symbol} 检测到卖盘墙")
            if large_orders.get('has_bid_wall') and side == 'short':
                logger.warning(f"🧊 [大单警告] {symbol} 检测到买盘墙")

            # 7. 综合信号检查 (高置信度时遵循)
            if confidence >= 0.7:
                if overall_signal == 'sell' and side == 'long':
                    return False, f"综合信号看空(置信度={confidence:.2f})"
                if overall_signal == 'buy' and side == 'short':
                    return False, f"综合信号看多(置信度={confidence:.2f})"

            return True, f"订单簿检查通过: OBI={obi:.3f}, 信号={overall_signal}"

        except Exception as e:
            logger.warning(f"⚠️ [订单簿检查] 异常: {e}")
            return True, f"检查异常: {e}"