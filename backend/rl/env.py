# -*- coding: utf-8 -*-
"""自定义 Gymnasium 交易环境

观测空间：价格 + 成交量 + 技术指标（SMA/EMA/RSI/MACD/ATR/Bollinger）
动作空间：离散 5（hold/buy/sell/close_long/close_short）

不依赖 axon_quant TradingEnv，完全自定义实现。
"""

from __future__ import annotations

from typing import Optional

import gymnasium as gym
import numpy as np
import pandas as pd


class TradingEnv(gym.Env):
    """自定义交易环境 — 丰富观测特征"""

    metadata = {"render_modes": []}

    def __init__(
        self,
        df: pd.DataFrame,
        initial_capital: float = 100_000,
        transaction_cost: float = 0.001,
        reward_fn=None,
        window_size: int = 20,
    ):
        """
        Args:
            df: OHLCV DataFrame（必须包含 Open/High/Low/Close/Volume）
            initial_capital: 初始资金
            transaction_cost: 手续费率
            reward_fn: 自定义奖励函数 (obs, action, info) -> float
            window_size: 技术指标计算窗口
        """
        super().__init__()

        self._df = df.copy()
        self._initial_capital = initial_capital
        self._transaction_cost = transaction_cost
        self._reward_fn = reward_fn
        self._window = window_size

        # 预计算技术指标
        self._features = self._compute_features(df)
        self._n_steps = len(self._features)

        # 动作空间：0=hold, 1=buy, 2=sell, 3=close_long, 4=close_short
        self.action_space = gym.spaces.Discrete(5)

        # 观测空间：[price_norm, volume_norm, sma_fast, sma_slow, ema, rsi, macd, bb_upper, bb_lower, atr, position]
        n_features = self._features.shape[1]
        self.observation_space = gym.spaces.Box(
            low=-np.inf, high=np.inf, shape=(n_features,), dtype=np.float32
        )

        # 状态
        self._step = 0
        self._position = 0.0  # 正=多头, 负=空头, 0=空仓
        self._entry_price = 0.0
        self._portfolio = initial_capital
        self._prev_portfolio = initial_capital
        self._trades = 0
        self._total_fees = 0.0

    def _compute_features(self, df: pd.DataFrame) -> np.ndarray:
        """计算技术指标特征"""
        close = df["Close"].values
        high = df["High"].values
        low = df["Low"].values
        volume = df["Volume"].values

        features = []

        # 1. 价格归一化（相对窗口内均值）
        sma_20 = self._sma(close, 20)
        price_norm = np.where(sma_20 > 0, (close - sma_20) / sma_20, 0)
        features.append(price_norm)

        # 2. 成交量归一化
        vol_ma = self._sma(volume, 20)
        vol_norm = np.where(vol_ma > 0, (volume - vol_ma) / vol_ma, 0)
        features.append(vol_norm)

        # 3. SMA 快线（相对价格）
        sma_fast = self._sma(close, 10)
        sma_fast_norm = np.where(close > 0, (sma_fast - close) / close, 0)
        features.append(sma_fast_norm)

        # 4. SMA 慢线（相对价格）
        sma_slow_norm = np.where(close > 0, (sma_20 - close) / close, 0)
        features.append(sma_slow_norm)

        # 5. EMA 12
        ema12 = self._ema(close, 12)
        ema_norm = np.where(close > 0, (ema12 - close) / close, 0)
        features.append(ema_norm)

        # 6. RSI
        rsi = self._rsi(close, 14)
        rsi_norm = (rsi - 50) / 50  # 归一化到 [-1, 1]
        features.append(rsi_norm)

        # 7. MACD
        macd, signal = self._macd(close)
        macd_norm = np.where(close > 0, macd / close, 0)
        features.append(macd_norm)

        # 8. MACD Signal
        signal_norm = np.where(close > 0, signal / close, 0)
        features.append(signal_norm)

        # 9. Bollinger Upper（相对价格）
        bb_upper, bb_lower = self._bollinger(close, 20)
        bb_up_norm = np.where(close > 0, (bb_upper - close) / close, 0)
        features.append(bb_up_norm)

        # 10. Bollinger Lower（相对价格）
        bb_low_norm = np.where(close > 0, (bb_lower - close) / close, 0)
        features.append(bb_low_norm)

        # 11. ATR（归一化）
        atr = self._atr(high, low, close, 14)
        atr_norm = np.where(close > 0, atr / close, 0)
        features.append(atr_norm)

        # 12. 价格变化率（动量）
        returns = np.zeros_like(close)
        returns[1:] = (close[1:] - close[:-1]) / np.where(close[:-1] > 0, close[:-1], 1)
        features.append(returns)

        # 转换为 (n_steps, n_features)
        result = np.column_stack(features).astype(np.float32)

        # 填充前 window_size 个 NaN
        result[:self._window] = 0

        return result

    @staticmethod
    def _sma(data: np.ndarray, period: int) -> np.ndarray:
        """简单移动平均"""
        result = np.zeros_like(data)
        for i in range(period - 1, len(data)):
            result[i] = np.mean(data[i - period + 1 : i + 1])
        return result

    @staticmethod
    def _ema(data: np.ndarray, period: int) -> np.ndarray:
        """指数移动平均"""
        result = np.zeros_like(data)
        alpha = 2 / (period + 1)
        result[0] = data[0]
        for i in range(1, len(data)):
            result[i] = alpha * data[i] + (1 - alpha) * result[i - 1]
        return result

    @staticmethod
    def _rsi(data: np.ndarray, period: int = 14) -> np.ndarray:
        """RSI 指标"""
        result = np.full_like(data, 50.0)
        deltas = np.diff(data)
        for i in range(period, len(data)):
            gains = deltas[i - period:i]
            up = np.mean(gains[gains > 0]) if np.any(gains > 0) else 0
            down = -np.mean(gains[gains < 0]) if np.any(gains < 0) else 0
            if down > 0:
                rs = up / down
                result[i] = 100 - 100 / (1 + rs)
            else:
                result[i] = 100 if up > 0 else 50
        return result

    @staticmethod
    def _macd(data: np.ndarray, fast: int = 12, slow: int = 26, signal: int = 9):
        """MACD 指标"""
        ema_fast = np.zeros_like(data)
        ema_slow = np.zeros_like(data)
        alpha_f = 2 / (fast + 1)
        alpha_s = 2 / (slow + 1)

        ema_fast[0] = data[0]
        ema_slow[0] = data[0]
        for i in range(1, len(data)):
            ema_fast[i] = alpha_f * data[i] + (1 - alpha_f) * ema_fast[i - 1]
            ema_slow[i] = alpha_s * data[i] + (1 - alpha_s) * ema_slow[i - 1]

        macd_line = ema_fast - ema_slow
        signal_line = np.zeros_like(data)
        alpha_sig = 2 / (signal + 1)
        signal_line[0] = macd_line[0]
        for i in range(1, len(data)):
            signal_line[i] = alpha_sig * macd_line[i] + (1 - alpha_sig) * signal_line[i - 1]

        return macd_line, signal_line

    @staticmethod
    def _bollinger(data: np.ndarray, period: int = 20, num_std: float = 2.0):
        """Bollinger Bands"""
        upper = np.zeros_like(data)
        lower = np.zeros_like(data)
        for i in range(period - 1, len(data)):
            window = data[i - period + 1 : i + 1]
            ma = np.mean(window)
            std = np.std(window)
            upper[i] = ma + num_std * std
            lower[i] = ma - num_std * std
        return upper, lower

    @staticmethod
    def _atr(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int = 14) -> np.ndarray:
        """ATR 指标"""
        tr = np.zeros_like(close)
        tr[0] = high[0] - low[0]
        for i in range(1, len(close)):
            tr[i] = max(high[i] - low[i], abs(high[i] - close[i - 1]), abs(low[i] - close[i - 1]))
        return TradingEnv._sma(tr, period)

    def reset(self, seed=None, options=None):
        super().reset(seed=seed)
        self._step = self._window
        self._position = 0.0
        self._entry_price = 0.0
        self._portfolio = self._initial_capital
        self._prev_portfolio = self._initial_capital
        self._trades = 0
        self._total_fees = 0.0
        obs = self._features[self._step]
        return obs, {}

    def step(self, action: int):
        close = self._df["Close"].values[self._step]
        prev_close = self._df["Close"].values[self._step - 1] if self._step > 0 else close
        price_change = close - prev_close

        # 执行交易
        if action == 1 and self._position <= 0:  # buy
            if self._position < 0:  # 先平空
                profit = (self._entry_price - close) * abs(self._position)
                fee = close * abs(self._position) * self._transaction_cost
                self._portfolio += profit - fee
                self._total_fees += fee
            # 开多
            qty = self._portfolio * 0.1 / close  # 用 10% 资金
            self._position = qty
            self._entry_price = close
            fee = close * qty * self._transaction_cost
            self._portfolio -= fee
            self._total_fees += fee
            self._trades += 1

        elif action == 2 and self._position >= 0:  # sell
            if self._position > 0:  # 先平多
                profit = (close - self._entry_price) * self._position
                fee = close * self._position * self._transaction_cost
                self._portfolio += profit - fee
                self._total_fees += fee
            # 开空
            qty = self._portfolio * 0.1 / close
            self._position = -qty
            self._entry_price = close
            fee = close * qty * self._transaction_cost
            self._portfolio -= fee
            self._total_fees += fee
            self._trades += 1

        elif action == 3 and self._position > 0:  # close long
            profit = (close - self._entry_price) * self._position
            fee = close * self._position * self._transaction_cost
            self._portfolio += profit - fee
            self._total_fees += fee
            self._position = 0.0
            self._trades += 1

        elif action == 4 and self._position < 0:  # close short
            profit = (self._entry_price - close) * abs(self._position)
            fee = close * abs(self._position) * self._transaction_cost
            self._portfolio += profit - fee
            self._total_fees += fee
            self._position = 0.0
            self._trades += 1

        # 持仓浮盈
        if self._position > 0:
            self._portfolio += price_change * self._position
        elif self._position < 0:
            self._portfolio += -price_change * abs(self._position)

        # 计算奖励
        if self._reward_fn is not None:
            info = {
                "portfolio_value": self._portfolio,
                "prev_portfolio": self._prev_portfolio,
                "trades": self._trades,
                "total_fees": self._total_fees,
                "position": self._position,
                "close": close,
            }
            reward = self._reward_fn(info)
        else:
            reward = (self._portfolio - self._prev_portfolio) / self._initial_capital * 100

        self._prev_portfolio = self._portfolio

        # 推进
        self._step += 1
        terminated = self._step >= self._n_steps
        truncated = self._portfolio <= 0

        obs = self._features[self._step] if self._step < self._n_steps else self._features[-1]
        info = {
            "portfolio_value": self._portfolio,
            "trades": self._trades,
            "total_fees": self._total_fees,
            "position": self._position,
        }

        return obs, reward, terminated, truncated, info

    def render(self):
        pass

    def close(self):
        pass
