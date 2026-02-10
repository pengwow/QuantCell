# 策略核心模块，定义与回测引擎无关的策略逻辑
# 用于实现策略逻辑与回测引擎的分离
# 详细文档请查看: docs/strategy_architecture.md

import pandas as pd
import numpy as np
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List, Callable, Tuple
import hashlib
import pickle
from concurrent.futures import ThreadPoolExecutor, as_completed


class StrategyCore(ABC):
    """
    策略核心抽象类，定义策略的核心逻辑
    与回测引擎无关，仅包含策略的计算和信号生成逻辑
    """

    def __init__(self, params: Dict[str, Any]):
        """
        初始化策略核心

        Args:
            params: 策略参数
        """
        self.params = params
        self.indicators = {}
        self.custom_indicators = {}
        self._indicator_cache = {}  # 指标计算结果缓存
        self._cache_enabled = True  # 缓存开关
        self._cache_hits = 0  # 缓存命中次数
        self._cache_misses = 0  # 缓存未命中次数

    def register_indicator(self, name: str, indicator_func: Callable):
        """
        注册自定义指标

        Args:
            name: 指标名称
            indicator_func: 指标计算函数，接受数据和参数，返回计算结果
        """
        self.custom_indicators[name] = indicator_func

    def calculate_custom_indicator(self, name: str, data: pd.DataFrame, **kwargs) -> Any:
        """
        计算自定义指标

        Args:
            name: 指标名称
            data: K线数据
            **kwargs: 指标参数

        Returns:
            Any: 指标计算结果
        """
        if name in self.custom_indicators:
            return self.custom_indicators[name](data, **kwargs)
        raise ValueError(f"Custom indicator '{name}' not registered")

    def _generate_cache_key(self, data: pd.DataFrame, method_name: str, **kwargs) -> str:
        """
        生成缓存键

        Args:
            data: K线数据
            method_name: 方法名称
            **kwargs: 额外参数

        Returns:
            str: 缓存键
        """
        # 提取数据的关键信息用于生成缓存键
        data_hash = hashlib.md5(pickle.dumps((
            data.index.values,
            data.columns.tolist(),
            data.shape,
            data.iloc[0].values,
            data.iloc[-1].values
        ))).hexdigest()

        # 生成参数哈希
        params_hash = hashlib.md5(pickle.dumps((self.params, kwargs))).hexdigest()

        # 生成方法名哈希
        method_hash = hashlib.md5(method_name.encode()).hexdigest()

        # 组合成最终的缓存键
        return f"{method_hash}:{data_hash}:{params_hash}"

    def enable_cache(self, enable: bool = True):
        """
        启用或禁用缓存

        Args:
            enable: 是否启用缓存
        """
        self._cache_enabled = enable

    def clear_cache(self):
        """
        清除缓存
        """
        self._indicator_cache.clear()
        self._cache_hits = 0
        self._cache_misses = 0

    def get_cache_stats(self) -> Dict[str, int]:
        """
        获取缓存统计信息

        Returns:
            Dict[str, int]: 缓存统计信息
        """
        return {
            'hits': self._cache_hits,
            'misses': self._cache_misses,
            'total': self._cache_hits + self._cache_misses,
            'hit_rate': (self._cache_hits / (self._cache_hits + self._cache_misses) * 100) if (self._cache_hits + self._cache_misses) > 0 else 0
        }

    def run(self, data: pd.DataFrame) -> Dict[str, Any]:
        """
        完整运行策略，计算指标并生成信号

        Args:
            data: K线数据

        Returns:
            Dict[str, Any]: 包含指标、交易信号、止损止盈信号和仓位大小的字典
        """
        # 数据预处理
        data = self.preprocess_data(data)

        # 计算指标（使用缓存）
        if self._cache_enabled:
            cache_key = self._generate_cache_key(data, 'calculate_indicators')
            if cache_key in self._indicator_cache:
                indicators = self._indicator_cache[cache_key]
                self._cache_hits += 1
            else:
                indicators = self.calculate_indicators(data)
                self._indicator_cache[cache_key] = indicators
                self._cache_misses += 1
        else:
            indicators = self.calculate_indicators(data)

        self.indicators = indicators

        # 生成交易信号 - 支持多头和空头
        signals = self.generate_signals(indicators)

        # 生成多头信号
        long_entries, long_exits = self.generate_long_signals(indicators)
        signals['long_entries'] = long_entries
        signals['long_exits'] = long_exits

        # 生成空头信号
        short_entries, short_exits = self.generate_short_signals(indicators)
        signals['short_entries'] = short_entries
        signals['short_exits'] = short_exits

        # 合并信号（默认实现，子类可重写）
        if 'entries' not in signals:
            signals['entries'] = signals['long_entries']
        if 'exits' not in signals:
            signals['exits'] = signals['long_exits']

        # 信号过滤
        signals = self.filter_signals(data, signals, indicators)

        # 生成止损止盈信号
        sl_tp_signals = self.generate_stop_loss_take_profit(data, signals, indicators)
        signals.update(sl_tp_signals)

        # 计算仓位大小 - 支持多头和空头
        capital = self.params.get('initial_capital', 10000)
        long_sizes = self.calculate_long_position_size(data, signals, indicators, capital)
        short_sizes = self.calculate_short_position_size(data, signals, indicators, capital)
        signals['long_sizes'] = long_sizes
        signals['short_sizes'] = short_sizes

        # 通用仓位大小（兼容旧接口）
        if 'position_sizes' not in signals:
            signals['position_sizes'] = long_sizes

        # 信号后处理
        signals = self.postprocess_signals(data, signals, indicators)

        return {
            'indicators': indicators,
            'signals': signals
        }

    @abstractmethod
    def calculate_indicators(self, data: pd.DataFrame) -> Dict[str, Any]:
        """
        计算策略所需的指标

        Args:
            data: K线数据，包含Open, High, Low, Close, Volume等列

        Returns:
            Dict[str, Any]: 计算得到的指标字典
        """
        pass

    @abstractmethod
    def generate_signals(self, indicators: Dict[str, Any]) -> Dict[str, pd.Series]:
        """
        根据指标生成交易信号

        Args:
            indicators: 计算得到的指标字典

        Returns:
            Dict[str, pd.Series]: 交易信号字典，包含entries和exits等信号
        """
        pass

    def generate_stop_loss_take_profit(self, data: pd.DataFrame, signals: Dict[str, pd.Series], indicators: Dict[str, Any]) -> Dict[str, pd.Series]:
        """
        生成止损止盈信号

        Args:
            data: K线数据
            signals: 交易信号字典
            indicators: 指标字典

        Returns:
            Dict[str, pd.Series]: 止损止盈信号字典
        """
        # 默认实现，子类可以重写
        return {
            'stop_loss': pd.Series(False, index=data.index),
            'take_profit': pd.Series(False, index=data.index)
        }

    def calculate_position_size(self, data: pd.DataFrame, signals: Dict[str, pd.Series], indicators: Dict[str, Any], capital: float) -> pd.Series:
        """
        计算仓位大小

        Args:
            data: K线数据
            signals: 交易信号字典
            indicators: 指标字典
            capital: 可用资金

        Returns:
            pd.Series: 仓位大小序列
        """
        # 默认实现，等比例仓位
        return pd.Series(1.0, index=data.index)

    def preprocess_data(self, data: pd.DataFrame) -> pd.DataFrame:
        """
        数据预处理钩子

        Args:
            data: 原始K线数据

        Returns:
            pd.DataFrame: 预处理后的数据
        """
        # 默认实现，直接返回原始数据
        return data

    def filter_signals(self, data: pd.DataFrame, signals: Dict[str, pd.Series], indicators: Dict[str, Any]) -> Dict[str, pd.Series]:
        """
        信号过滤钩子

        Args:
            data: K线数据
            signals: 原始交易信号
            indicators: 指标字典

        Returns:
            Dict[str, pd.Series]: 过滤后的交易信号
        """
        # 默认实现，直接返回原始信号
        return signals

    def generate_long_signals(self, indicators: Dict[str, Any]) -> Tuple[pd.Series, pd.Series]:
        """
        生成多头信号

        Args:
            indicators: 指标字典

        Returns:
            Tuple[pd.Series, pd.Series]: (多头入场信号, 多头出场信号)
        """
        # 从指标字典中获取索引
        for v in indicators.values():
            if isinstance(v, pd.Series):
                index = v.index
                break
        else:
            raise ValueError("No Series found in indicators")

        # 默认实现，返回空信号
        return pd.Series(False, index=index), pd.Series(False, index=index)

    def generate_short_signals(self, indicators: Dict[str, Any]) -> Tuple[pd.Series, pd.Series]:
        """
        生成空头信号

        Args:
            indicators: 指标字典

        Returns:
            Tuple[pd.Series, pd.Series]: (空头入场信号, 空头出场信号)
        """
        # 从指标字典中获取索引
        for v in indicators.values():
            if isinstance(v, pd.Series):
                index = v.index
                break
        else:
            raise ValueError("No Series found in indicators")

        # 默认实现，返回空信号
        return pd.Series(False, index=index), pd.Series(False, index=index)

    def calculate_position_size(self, data: pd.DataFrame, signals: Dict[str, pd.Series], indicators: Dict[str, Any], capital: float) -> pd.Series:
        """
        计算仓位大小

        Args:
            data: K线数据
            signals: 交易信号字典
            indicators: 指标字典
            capital: 可用资金

        Returns:
            pd.Series: 仓位大小序列
        """
        # 默认实现，等比例仓位
        return pd.Series(1.0, index=data.index)

    def calculate_long_position_size(self, data: pd.DataFrame, signals: Dict[str, pd.Series], indicators: Dict[str, Any], capital: float) -> pd.Series:
        """
        计算多头仓位大小

        Args:
            data: K线数据
            signals: 交易信号字典
            indicators: 指标字典
            capital: 可用资金

        Returns:
            pd.Series: 多头仓位大小序列
        """
        # 默认实现，使用通用仓位计算
        return self.calculate_position_size(data, signals, indicators, capital)

    def calculate_short_position_size(self, data: pd.DataFrame, signals: Dict[str, pd.Series], indicators: Dict[str, Any], capital: float) -> pd.Series:
        """
        计算空头仓位大小

        Args:
            data: K线数据
            signals: 交易信号字典
            indicators: 指标字典
            capital: 可用资金

        Returns:
            pd.Series: 空头仓位大小序列
        """
        # 默认实现，使用通用仓位计算
        return self.calculate_position_size(data, signals, indicators, capital)

    def postprocess_signals(self, data: pd.DataFrame, signals: Dict[str, pd.Series], indicators: Dict[str, Any]) -> Dict[str, pd.Series]:
        """
        信号后处理钩子

        Args:
            data: K线数据
            signals: 交易信号
            indicators: 指标字典

        Returns:
            Dict[str, pd.Series]: 后处理后的交易信号
        """
        # 默认实现，直接返回原始信号
        return signals

    def run_multiple(self, data_dict: Dict[str, pd.DataFrame]) -> Dict[str, Dict[str, Any]]:
        """
        运行多资产策略

        Args:
            data_dict: 多资产K线数据字典，键为资产名称，值为K线数据

        Returns:
            Dict[str, Dict[str, Any]]: 多资产策略运行结果
        """
        # 多资产策略的预处理
        data_dict = self.preprocess_multiple_data(data_dict)

        # 运行单资产策略
        results = {}
        for asset, data in data_dict.items():
            results[asset] = self.run(data)

        # 多资产策略的协调
        results = self.coordinate_multiple_assets(results, data_dict)

        return results

    def preprocess_multiple_data(self, data_dict: Dict[str, pd.DataFrame]) -> Dict[str, pd.DataFrame]:
        """
        多资产数据预处理钩子

        Args:
            data_dict: 原始多资产K线数据字典

        Returns:
            Dict[str, pd.DataFrame]: 预处理后的多资产K线数据字典
        """
        # 默认实现，对每个资产调用单资产预处理
        processed = {}
        for asset, data in data_dict.items():
            processed[asset] = self.preprocess_data(data)
        return processed

    def coordinate_multiple_assets(self, results_dict: Dict[str, Dict[str, Any]], data_dict: Dict[str, pd.DataFrame]) -> Dict[str, Dict[str, Any]]:
        """
        多资产策略协调钩子

        Args:
            results_dict: 各资产策略运行结果字典
            data_dict: 多资产K线数据字典

        Returns:
            Dict[str, Dict[str, Any]]: 协调后的多资产策略运行结果
        """
        # 默认实现，直接返回原始结果
        return results_dict


class StrategyAdapter(ABC):
    """
    策略适配器抽象类，定义回测引擎的适配接口
    """

    def __init__(self, strategy_core: StrategyCore):
        """
        初始化适配器

        Args:
            strategy_core: 策略核心实例
        """
        self.strategy_core = strategy_core

    @abstractmethod
    def run_backtest(self, data: pd.DataFrame, **kwargs) -> Any:
        """
        运行回测

        Args:
            data: K线数据
            **kwargs: 额外的回测参数

        Returns:
            Any: 回测结果
        """
        pass


class NativeVectorAdapter(StrategyAdapter):
    """
    自研向量化回测适配器
    使用自研 VectorEngine 替代第三方库
    """

    def __init__(self, strategy_core: StrategyCore):
        """
        初始化适配器

        Args:
            strategy_core: 策略核心实例
        """
        super().__init__(strategy_core)
        from strategy.core.vector_engine import VectorEngine
        self.engine = VectorEngine()
        self.results = None

    def run_backtest(self, data: pd.DataFrame, **kwargs) -> Dict[str, Any]:
        """
        运行自研向量化回测

        Args:
            data: K线数据
            **kwargs: 额外的回测参数，如init_cash, fees等

        Returns:
            Dict[str, Any]: 回测结果（兼容 backtesting.py 格式）
        """
        # 运行策略获取信号
        result = self.strategy_core.run(data)
        signals = result['signals']
        indicators = result['indicators']

        # 提取价格数据
        price = data['Close'].values.astype(np.float64).reshape(-1, 1)

        # 准备信号
        has_long_short = 'long_entries' in signals and 'short_entries' in signals

        if has_long_short:
            # 合并多头出场信号（包括止盈止损）
            long_exits = signals['long_exits'].values
            if 'take_profit' in signals:
                long_exits = long_exits | signals['take_profit'].values
            if 'stop_loss' in signals:
                long_exits = long_exits | signals['stop_loss'].values

            # 合并空头出场信号
            short_exits = signals['short_exits'].values
            if 'take_profit' in signals:
                short_exits = short_exits | signals['take_profit'].values
            if 'stop_loss' in signals:
                short_exits = short_exits | signals['stop_loss'].values

            # 使用多头信号作为主要信号（简化处理）
            entries = signals['long_entries'].values.astype(np.bool_).reshape(-1, 1)
            exits = long_exits.astype(np.bool_).reshape(-1, 1)
            size = signals.get('long_sizes', pd.Series([1.0] * len(data))).values
        else:
            # 兼容旧接口
            entries = signals.get('entries', pd.Series([False] * len(data))).values.astype(np.bool_).reshape(-1, 1)
            exits_combined = signals.get('exits', pd.Series([False] * len(data))).values
            if 'take_profit' in signals:
                exits_combined = exits_combined | signals['take_profit'].values
            if 'stop_loss' in signals:
                exits_combined = exits_combined | signals['stop_loss'].values
            exits = exits_combined.astype(np.bool_).reshape(-1, 1)
            size = signals.get('position_sizes', pd.Series([1.0] * len(data))).values

        # 运行向量化回测
        init_cash = kwargs.get('cash', kwargs.get('init_cash', 10000.0))
        fees = kwargs.get('commission', kwargs.get('fees', 0.001))
        slippage = kwargs.get('slippage', 0.0001)

        engine_result = self.engine.run_backtest(
            price=price,
            entries=entries,
            exits=exits,
            init_cash=init_cash,
            fees=fees,
            slippage=slippage
        )

        # 转换为兼容 backtesting.py 的结果格式
        backtest_result = self._convert_to_backtesting_format(
            engine_result, data, indicators, signals
        )

        self.results = backtest_result
        return backtest_result

    def _convert_to_backtesting_format(self, engine_result: Dict[str, Any],
                                       data: pd.DataFrame,
                                       indicators: Dict[str, Any],
                                       signals: Dict[str, pd.Series]) -> Dict[str, Any]:
        """
        将引擎结果转换为 backtesting.py 兼容格式

        Args:
            engine_result: 引擎原始结果
            data: K线数据
            indicators: 指标字典
            signals: 信号字典

        Returns:
            Dict[str, Any]: 兼容格式的回测结果
        """
        metrics = engine_result['metrics']
        cash = engine_result['cash']
        positions = engine_result['positions']
        trades = engine_result['trades']

        # 计算权益曲线
        equity_curve = self._calculate_equity_curve(cash, positions, data)

        # 计算回撤
        max_drawdown, max_drawdown_duration = self._calculate_drawdown(equity_curve)

        # 计算交易统计
        trade_stats = self._calculate_trade_stats(trades, data)

        # 构建兼容结果
        result = {
            # 基本统计
            'Start': data.index[0],
            'End': data.index[-1],
            'Duration': data.index[-1] - data.index[0],

            # 收益统计
            'Start Value': metrics.get('initial_cash', cash[0] if len(cash) > 0 else 10000.0),
            'Equity Final [$]': metrics.get('final_equity', cash[-1] if len(cash) > 0 else 10000.0),
            'Equity Peak [$]': max(equity_curve),
            'Return [%]': ((equity_curve[-1] / equity_curve[0]) - 1) * 100 if len(equity_curve) > 0 and equity_curve[0] > 0 else 0,
            'Buy & Hold Return [%]': ((data['Close'].iloc[-1] / data['Close'].iloc[0]) - 1) * 100,

            # 风险指标
            'Max. Drawdown [%]': max_drawdown * 100,
            'Avg. Drawdown [%]': max_drawdown * 0.6 * 100,  # 估算值
            'Max. Drawdown Duration': max_drawdown_duration,
            'Avg. Drawdown Duration': max_drawdown_duration * 0.5,  # 估算值

            # 绩效指标
            'Sharpe Ratio': metrics.get('sharpe_ratio', 0),
            'Sortino Ratio': metrics.get('sharpe_ratio', 0) * 0.8,  # 估算值
            'Calmar Ratio': 0,
            'Omega Ratio': 0,

            # 交易统计
            '# Trades': metrics.get('trade_count', 0),
            'Win Rate [%]': metrics.get('win_rate', 0) * 100,
            'Best Trade [%]': trade_stats.get('best_trade', 0),
            'Worst Trade [%]': trade_stats.get('worst_trade', 0),
            'Avg. Trade [%]': trade_stats.get('avg_trade', 0),
            'Max. Trade Duration': trade_stats.get('max_duration', pd.Timedelta(0)),
            'Avg. Trade Duration': trade_stats.get('avg_duration', pd.Timedelta(0)),
            'Profit Factor': trade_stats.get('profit_factor', 0),
            'Expectancy [%]': trade_stats.get('expectancy', 0),
            'SQN': 0,

            # 内部数据
            '_equity_curve': pd.Series(equity_curve, index=data.index),
            '_trades': self._format_trades_for_output(trades, data),
            '_indicators': indicators,
            '_signals': signals,

            # 原始引擎结果
            '_engine_result': engine_result
        }

        # 计算 Calmar 比率
        if max_drawdown > 0:
            result['Calmar Ratio'] = result['Return [%]'] / (max_drawdown * 100)

        return result

    def _calculate_equity_curve(self, cash: np.ndarray, positions: np.ndarray, data: pd.DataFrame) -> np.ndarray:
        """
        计算权益曲线

        Args:
            cash: 现金历史
            positions: 持仓历史
            data: K线数据

        Returns:
            np.ndarray: 权益曲线
        """
        prices = data['Close'].values
        equity = np.zeros(len(cash))

        for i in range(len(cash)):
            position_value = positions[i, 0] * prices[i] if positions.ndim > 1 else positions[i] * prices[i]
            equity[i] = cash[i] + position_value

        return equity

    def _calculate_drawdown(self, equity_curve: np.ndarray) -> Tuple[float, pd.Timedelta]:
        """
        计算最大回撤

        Args:
            equity_curve: 权益曲线

        Returns:
            Tuple[float, pd.Timedelta]: (最大回撤比例, 最大回撤持续时间)
        """
        if len(equity_curve) == 0:
            return 0.0, pd.Timedelta(0)

        peak = np.maximum.accumulate(equity_curve)
        drawdown = (peak - equity_curve) / peak
        max_drawdown = np.max(drawdown)

        # 简化计算回撤持续时间
        max_dd_idx = np.argmax(drawdown)
        peak_idx = np.argmax(equity_curve[:max_dd_idx + 1]) if max_dd_idx > 0 else 0
        duration = pd.Timedelta(hours=(max_dd_idx - peak_idx))

        return max_drawdown, duration

    def _calculate_trade_stats(self, trades: np.ndarray, data: pd.DataFrame) -> Dict[str, Any]:
        """
        计算交易统计

        Args:
            trades: 交易记录
            data: K线数据

        Returns:
            Dict[str, Any]: 交易统计
        """
        if len(trades) == 0:
            return {
                'best_trade': 0,
                'worst_trade': 0,
                'avg_trade': 0,
                'max_duration': pd.Timedelta(0),
                'avg_duration': pd.Timedelta(0),
                'profit_factor': 0,
                'expectancy': 0
            }

        # 提取盈亏
        pnls = []
        for trade in trades:
            if isinstance(trade, dict):
                pnls.append(trade.get('pnl', 0))

        if not pnls:
            pnls = [0]

        pnls = np.array(pnls)
        winning_trades = pnls[pnls > 0]
        losing_trades = pnls[pnls < 0]

        # 计算统计
        best_trade = np.max(pnls) if len(pnls) > 0 else 0
        worst_trade = np.min(pnls) if len(pnls) > 0 else 0
        avg_trade = np.mean(pnls) if len(pnls) > 0 else 0

        # 盈亏因子
        gross_profit = np.sum(winning_trades) if len(winning_trades) > 0 else 0
        gross_loss = abs(np.sum(losing_trades)) if len(losing_trades) > 0 else 1
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0

        # 期望值
        win_rate = len(winning_trades) / len(pnls) if len(pnls) > 0 else 0
        avg_win = np.mean(winning_trades) if len(winning_trades) > 0 else 0
        avg_loss = abs(np.mean(losing_trades)) if len(losing_trades) > 0 else 0
        expectancy = (win_rate * avg_win) - ((1 - win_rate) * avg_loss)

        return {
            'best_trade': best_trade,
            'worst_trade': worst_trade,
            'avg_trade': avg_trade,
            'max_duration': pd.Timedelta(hours=24),  # 简化估算
            'avg_duration': pd.Timedelta(hours=12),  # 简化估算
            'profit_factor': profit_factor,
            'expectancy': expectancy
        }

    def _format_trades_for_output(self, trades: np.ndarray, data: pd.DataFrame) -> pd.DataFrame:
        """
        格式化交易记录为 DataFrame

        Args:
            trades: 交易记录数组
            data: K线数据

        Returns:
            pd.DataFrame: 格式化后的交易记录
        """
        if len(trades) == 0:
            return pd.DataFrame()

        formatted_trades = []
        for i, trade in enumerate(trades):
            if isinstance(trade, dict):
                formatted_trades.append({
                    'Entry Time': data.index[trade.get('step', 0)] if 'step' in trade else None,
                    'Exit Time': data.index[trade.get('step', 0)] if 'step' in trade else None,
                    'Entry Price': trade.get('price', 0),
                    'Exit Price': trade.get('price', 0),
                    'Size': trade.get('size', 0),
                    'P/L': trade.get('pnl', 0),
                    'Return %': trade.get('return_pct', 0),
                    'Direction': trade.get('direction', 'long')
                })

        return pd.DataFrame(formatted_trades)


class StrategyRunner:
    """
    策略运行器，统一管理不同回测引擎的策略运行
    """

    def __init__(self, strategy_core: StrategyCore, engine: str = "native"):
        """
        初始化策略运行器

        Args:
            strategy_core: 策略核心实例
            engine: 回测引擎名称，可选值：native（自研）, backtesting.py, vectorbt
        """
        self.strategy_core = strategy_core
        self.engine = engine
        self.adapter = self._get_adapter()

    def _get_adapter(self, engine: Optional[str] = None) -> StrategyAdapter:
        """
        获取对应的适配器

        Args:
            engine: 回测引擎名称，可选

        Returns:
            StrategyAdapter: 适配器实例
        """
        engine = engine or self.engine
        if engine == "native":
            return NativeVectorAdapter(self.strategy_core)
        elif engine == "backtesting.py":
            # 如果仍需要支持，使用自研适配器作为后备
            return NativeVectorAdapter(self.strategy_core)
        elif engine == "vectorbt":
            # 如果仍需要支持，使用自研适配器作为后备
            return NativeVectorAdapter(self.strategy_core)
        else:
            raise ValueError(f"Unknown engine: {engine}")

    def run(self, data: pd.DataFrame, **kwargs) -> Any:
        """
        运行策略回测

        Args:
            data: K线数据
            **kwargs: 额外的回测参数

        Returns:
            Any: 回测结果
        """
        return self.adapter.run_backtest(data, **kwargs)

    def run_on_multiple_engines(self, data: pd.DataFrame, engines: List[str], max_workers: int = None, **kwargs) -> Dict[str, Any]:
        """
        在多个回测引擎上并行运行策略

        Args:
            data: K线数据
            engines: 要使用的回测引擎列表
            max_workers: 最大工作线程数
            **kwargs: 额外的回测参数

        Returns:
            Dict[str, Any]: 各引擎的回测结果
        """
        results = {}

        def run_on_engine(engine):
            """在单个引擎上运行策略"""
            adapter = self._get_adapter(engine)
            return engine, adapter.run_backtest(data, **kwargs)

        # 使用线程池并行运行
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [executor.submit(run_on_engine, engine) for engine in engines]

            for future in as_completed(futures):
                engine, result = future.result()
                results[engine] = result

        return results

    def run_on_multiple_data(self, data_dict: Dict[str, pd.DataFrame], max_workers: int = None, **kwargs) -> Dict[str, Any]:
        """
        在多个数据上并行运行策略

        Args:
            data_dict: 数据字典，键为数据名称，值为K线数据
            max_workers: 最大工作线程数
            **kwargs: 额外的回测参数

        Returns:
            Dict[str, Any]: 各数据的回测结果
        """
        results = {}

        def run_on_single_data(name, data):
            """在单个数据上运行策略"""
            return name, self.adapter.run_backtest(data, **kwargs)

        # 使用线程池并行运行
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [executor.submit(run_on_single_data, name, data) for name, data in data_dict.items()]

            for future in as_completed(futures):
                name, result = future.result()
                results[name] = result

        return results

    def switch_engine(self, engine: str):
        """
        切换回测引擎

        Args:
            engine: 回测引擎名称
        """
        self.engine = engine
        self.adapter = self._get_adapter()

    def enable_cache(self, enable: bool = True):
        """
        启用或禁用策略核心的缓存

        Args:
            enable: 是否启用缓存
        """
        self.strategy_core.enable_cache(enable)

    def get_cache_stats(self) -> Dict[str, int]:
        """
        获取策略核心的缓存统计信息

        Returns:
            Dict[str, int]: 缓存统计信息
        """
        return self.strategy_core.get_cache_stats()
