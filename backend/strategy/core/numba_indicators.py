#!/usr/bin/env python3
"""
Numba优化的技术指标计算库

提供高性能的JIT编译技术指标计算函数
"""

import numpy as np
from numba import njit, prange
from typing import Tuple


@njit(cache=True, fastmath=True)
def calculate_sma_numba(prices: np.ndarray, period: int) -> np.ndarray:
    """
    Numba优化的简单移动平均线(SMA)计算
    
    Args:
        prices: 价格数组
        period: 计算周期
        
    Returns:
        SMA数组
    """
    n = len(prices)
    sma = np.zeros(n)
    
    # 前period-1个值为NaN
    for i in range(min(period - 1, n)):
        sma[i] = np.nan
    
    # 计算第一个有效值
    if n >= period:
        sma[period - 1] = np.mean(prices[:period])
        
        # 使用滑动窗口优化
        for i in range(period, n):
            sma[i] = sma[i - 1] + (prices[i] - prices[i - period]) / period
    
    return sma


@njit(cache=True, fastmath=True)
def calculate_ema_numba(prices: np.ndarray, period: int) -> np.ndarray:
    """
    Numba优化的指数移动平均线(EMA)计算
    
    Args:
        prices: 价格数组
        period: 计算周期
        
    Returns:
        EMA数组
    """
    n = len(prices)
    ema = np.zeros(n)
    
    # 平滑系数
    alpha = 2.0 / (period + 1)
    
    # 第一个值使用SMA
    ema[0] = prices[0]
    
    # 递归计算EMA
    for i in range(1, n):
        ema[i] = alpha * prices[i] + (1 - alpha) * ema[i - 1]
    
    return ema


@njit(cache=True, fastmath=True)
def calculate_rsi_numba(prices: np.ndarray, period: int = 14) -> np.ndarray:
    """
    Numba优化的相对强弱指标(RSI)计算
    
    Args:
        prices: 价格数组
        period: 计算周期，默认14
        
    Returns:
        RSI数组
    """
    n = len(prices)
    rsi = np.zeros(n)
    
    # 计算价格变化
    deltas = np.zeros(n)
    for i in range(1, n):
        deltas[i] = prices[i] - prices[i - 1]
    
    # 分离上涨和下跌
    gains = np.zeros(n)
    losses = np.zeros(n)
    for i in range(n):
        if deltas[i] > 0:
            gains[i] = deltas[i]
        else:
            losses[i] = -deltas[i]
    
    # 计算平均收益和损失
    avg_gains = np.zeros(n)
    avg_losses = np.zeros(n)
    
    # 第一个有效值
    if n > period:
        avg_gains[period] = np.mean(gains[1:period+1])
        avg_losses[period] = np.mean(losses[1:period+1])
        
        # 平滑计算
        for i in range(period + 1, n):
            avg_gains[i] = (avg_gains[i-1] * (period - 1) + gains[i]) / period
            avg_losses[i] = (avg_losses[i-1] * (period - 1) + losses[i]) / period
    
    # 计算RSI
    for i in range(period, n):
        if avg_losses[i] == 0:
            rsi[i] = 100.0
        else:
            rs = avg_gains[i] / avg_losses[i]
            rsi[i] = 100.0 - (100.0 / (1.0 + rs))
    
    # 前period个值为NaN
    for i in range(min(period, n)):
        rsi[i] = np.nan
    
    return rsi


@njit(cache=True, fastmath=True)
def calculate_macd_numba(prices: np.ndarray, fast: int = 12, slow: int = 26, signal: int = 9) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Numba优化的MACD指标计算
    
    Args:
        prices: 价格数组
        fast: 快速EMA周期，默认12
        slow: 慢速EMA周期，默认26
        signal: 信号线周期，默认9
        
    Returns:
        (MACD线, 信号线, 柱状图)
    """
    ema_fast = calculate_ema_numba(prices, fast)
    ema_slow = calculate_ema_numba(prices, slow)
    
    # MACD线
    macd_line = ema_fast - ema_slow
    
    # 信号线
    signal_line = calculate_ema_numba(macd_line, signal)
    
    # 柱状图
    histogram = macd_line - signal_line
    
    return macd_line, signal_line, histogram


@njit(cache=True, fastmath=True)
def calculate_bollinger_bands_numba(prices: np.ndarray, period: int = 20, std_dev: float = 2.0) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Numba优化的布林带计算
    
    Args:
        prices: 价格数组
        period: 计算周期，默认20
        std_dev: 标准差倍数，默认2.0
        
    Returns:
        (上轨, 中轨, 下轨)
    """
    n = len(prices)
    middle = calculate_sma_numba(prices, period)
    
    upper = np.zeros(n)
    lower = np.zeros(n)
    
    for i in range(period - 1, n):
        window = prices[i - period + 1:i + 1]
        std = np.std(window)
        upper[i] = middle[i] + std_dev * std
        lower[i] = middle[i] - std_dev * std
    
    # 前period-1个值为NaN
    for i in range(min(period - 1, n)):
        upper[i] = np.nan
        lower[i] = np.nan
    
    return upper, middle, lower


@njit(cache=True, fastmath=True)
def calculate_crossover_signals_numba(fast: np.ndarray, slow: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """
    Numba优化的交叉信号生成
    
    Args:
        fast: 快速线数组
        slow: 慢速线数组
        
    Returns:
        (买入信号数组, 卖出信号数组)
    """
    n = len(fast)
    entries = np.zeros(n, dtype=np.bool_)
    exits = np.zeros(n, dtype=np.bool_)
    
    for i in range(1, n):
        # 金叉：快速线上穿慢速线
        if fast[i] > slow[i] and fast[i-1] <= slow[i-1]:
            entries[i] = True
        
        # 死叉：快速线下穿慢速线
        if fast[i] < slow[i] and fast[i-1] >= slow[i-1]:
            exits[i] = True
    
    return entries, exits


@njit(cache=True, fastmath=True, parallel=True)
def calculate_multiple_sma_numba(prices: np.ndarray, periods: np.ndarray) -> np.ndarray:
    """
    并行计算多个SMA指标
    
    Args:
        prices: 价格数组
        periods: 周期数组
        
    Returns:
        二维数组，每行对应一个周期的SMA
    """
    n_periods = len(periods)
    n_prices = len(prices)
    results = np.zeros((n_periods, n_prices))
    
    for i in prange(n_periods):
        results[i] = calculate_sma_numba(prices, periods[i])
    
    return results


@njit(cache=True, fastmath=True)
def calculate_atr_numba(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int = 14) -> np.ndarray:
    """
    Numba优化的平均真实波幅(ATR)计算
    
    Args:
        high: 最高价数组
        low: 最低价数组
        close: 收盘价数组
        period: 计算周期，默认14
        
    Returns:
        ATR数组
    """
    n = len(close)
    tr = np.zeros(n)
    
    # 计算真实波幅
    tr[0] = high[0] - low[0]
    for i in range(1, n):
        tr1 = high[i] - low[i]
        tr2 = abs(high[i] - close[i-1])
        tr3 = abs(low[i] - close[i-1])
        tr[i] = max(tr1, max(tr2, tr3))
    
    # 计算ATR
    atr = np.zeros(n)
    if n >= period:
        atr[period-1] = np.mean(tr[:period])
        for i in range(period, n):
            atr[i] = (atr[i-1] * (period - 1) + tr[i]) / period
    
    # 前period-1个值为NaN
    for i in range(min(period - 1, n)):
        atr[i] = np.nan
    
    return atr
