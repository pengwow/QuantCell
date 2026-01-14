# 常见策略实现
# 包括 RSI、MACD、Bollinger Bands 等策略

import pandas as pd
import numpy as np
from .core import StrategyCore


class RSIStrategy(StrategyCore):
    """
    RSI 策略
    当 RSI 低于超卖阈值时买入，高于超买阈值时卖出
    """
    
    def calculate_indicators(self, data):
        """
        计算 RSI 指标
        """
        # 获取参数
        rsi_period = self.params.get('rsi_period', 14)
        
        # 计算 RSI
        close = data['Close']
        delta = close.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=rsi_period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=rsi_period).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        
        return {
            'rsi': rsi
        }
    
    def generate_signals(self, indicators):
        """
        根据 RSI 指标生成交易信号
        """
        rsi = indicators['rsi']
        
        # 获取参数
        oversold = self.params.get('oversold', 30)
        overbought = self.params.get('overbought', 70)
        
        # 生成信号
        entries = rsi < oversold
        exits = rsi > overbought
        
        return {
            'entries': entries,
            'exits': exits
        }
    
    def generate_stop_loss_take_profit(self, data, signals, indicators):
        """
        生成止损止盈信号
        """
        # 获取参数
        stop_loss_pct = self.params.get('stop_loss_pct', 0.02)
        take_profit_pct = self.params.get('take_profit_pct', 0.05)
        
        # 生成信号（这里使用简单的固定比例止损止盈，实际实现需要跟踪持仓价格）
        return {
            'stop_loss': pd.Series(False, index=data.index),
            'take_profit': pd.Series(False, index=data.index)
        }


class MACDStrategy(StrategyCore):
    """
    MACD 策略
    当 MACD 线上穿信号线时买入，下穿信号线时卖出
    """
    
    def calculate_indicators(self, data):
        """
        计算 MACD 指标
        """
        # 获取参数
        fast_period = self.params.get('fast_period', 12)
        slow_period = self.params.get('slow_period', 26)
        signal_period = self.params.get('signal_period', 9)
        
        # 计算 MACD
        close = data['Close']
        ema_fast = close.ewm(span=fast_period).mean()
        ema_slow = close.ewm(span=slow_period).mean()
        macd_line = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=signal_period).mean()
        histogram = macd_line - signal_line
        
        return {
            'macd_line': macd_line,
            'signal_line': signal_line,
            'histogram': histogram
        }
    
    def generate_signals(self, indicators):
        """
        根据 MACD 指标生成交易信号
        """
        macd_line = indicators['macd_line']
        signal_line = indicators['signal_line']
        
        # 生成信号
        entries = (macd_line > signal_line) & (macd_line.shift(1) <= signal_line.shift(1))
        exits = (macd_line < signal_line) & (macd_line.shift(1) >= signal_line.shift(1))
        
        return {
            'entries': entries,
            'exits': exits
        }


class BollingerBandsStrategy(StrategyCore):
    """
    Bollinger Bands 策略
    当价格触及下轨时买入，触及上轨时卖出
    """
    
    def calculate_indicators(self, data):
        """
        计算 Bollinger Bands 指标
        """
        # 获取参数
        bb_period = self.params.get('bb_period', 20)
        bb_std = self.params.get('bb_std', 2)
        
        # 计算 Bollinger Bands
        close = data['Close']
        sma = close.rolling(window=bb_period).mean()
        std = close.rolling(window=bb_period).std()
        upper_band = sma + (std * bb_std)
        lower_band = sma - (std * bb_std)
        
        return {
            'close': close,
            'sma': sma,
            'upper_band': upper_band,
            'lower_band': lower_band
        }
    
    def generate_signals(self, indicators):
        """
        根据 Bollinger Bands 指标生成交易信号
        """
        # 从数据中获取收盘价（注意：这里需要确保在 calculate_indicators 中保存了收盘价）
        # 或者在 run 方法中传递完整的数据
        # 这里简化处理，假设 indicators 中包含收盘价
        if 'close' in indicators:
            close = indicators['close']
        else:
            # 如果没有收盘价，抛出错误
            raise ValueError("Close price not found in indicators")
        
        upper_band = indicators['upper_band']
        lower_band = indicators['lower_band']
        
        # 生成信号
        entries = close <= lower_band
        exits = close >= upper_band
        
        return {
            'entries': entries,
            'exits': exits
        }


class MultiFactorStrategy(StrategyCore):
    """
    多因子策略
    结合多个指标生成交易信号
    """
    
    def calculate_indicators(self, data):
        """
        计算多个指标
        """
        # 计算 RSI
        rsi_period = self.params.get('rsi_period', 14)
        delta = data['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=rsi_period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=rsi_period).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        
        # 计算 MACD
        fast_period = self.params.get('fast_period', 12)
        slow_period = self.params.get('slow_period', 26)
        signal_period = self.params.get('signal_period', 9)
        ema_fast = data['Close'].ewm(span=fast_period).mean()
        ema_slow = data['Close'].ewm(span=slow_period).mean()
        macd_line = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=signal_period).mean()
        
        # 计算 SMA 交叉
        short_sma_period = self.params.get('short_sma_period', 10)
        long_sma_period = self.params.get('long_sma_period', 20)
        short_sma = data['Close'].rolling(window=short_sma_period).mean()
        long_sma = data['Close'].rolling(window=long_sma_period).mean()
        
        return {
            'rsi': rsi,
            'macd_line': macd_line,
            'signal_line': signal_line,
            'short_sma': short_sma,
            'long_sma': long_sma
        }
    
    def generate_signals(self, indicators):
        """
        根据多个指标生成交易信号
        """
        rsi = indicators['rsi']
        macd_line = indicators['macd_line']
        signal_line = indicators['signal_line']
        short_sma = indicators['short_sma']
        long_sma = indicators['long_sma']
        
        # 获取参数
        rsi_oversold = self.params.get('rsi_oversold', 40)
        
        # 多因子信号
        # 1. RSI 低于超卖阈值
        factor1 = rsi < rsi_oversold
        # 2. MACD 线上穿信号线
        factor2 = (macd_line > signal_line) & (macd_line.shift(1) <= signal_line.shift(1))
        # 3. 短期均线上穿长期均线
        factor3 = (short_sma > long_sma) & (short_sma.shift(1) <= long_sma.shift(1))
        
        # 综合信号（三个因子中至少两个满足）
        entries = (factor1 & factor2) | (factor1 & factor3) | (factor2 & factor3)
        
        # 卖出信号（RSI 高于 70 或短期均线下穿长期均线）
        exits = (rsi > 70) | ((short_sma < long_sma) & (short_sma.shift(1) >= long_sma.shift(1)))
        
        return {
            'entries': entries,
            'exits': exits
        }
    
    def calculate_position_size(self, data, signals, indicators, capital):
        """
        根据指标动态调整仓位大小
        """
        rsi = indicators['rsi']
        
        # 根据 RSI 值调整仓位大小（RSI 越低，仓位越大）
        position_size = (50 - rsi) / 50
        position_size = position_size.clip(0.2, 1.0)  # 限制仓位在 20% 到 100% 之间
        
        return position_size
