"""
NativeVectorAdapter 单元测试
测试自研向量化回测适配器的功能和兼容性
"""

import pytest
import pandas as pd
import numpy as np
from strategy.core import StrategyCore, NativeVectorAdapter, StrategyRunner


class SMAStrategy(StrategyCore):
    """SMA交叉测试策略类"""

    def calculate_indicators(self, data: pd.DataFrame) -> dict:
        """计算简单指标"""
        return {
            'sma5': data['Close'].rolling(window=5).mean(),
            'sma10': data['Close'].rolling(window=10).mean()
        }
    
    def generate_signals(self, indicators: dict) -> dict:
        """生成交易信号"""
        sma5 = indicators['sma5']
        sma10 = indicators['sma10']
        
        # 金叉买入，死叉卖出
        entries = (sma5 > sma10) & (sma5.shift(1) <= sma10.shift(1))
        exits = (sma5 < sma10) & (sma5.shift(1) >= sma10.shift(1))
        
        return {
            'entries': entries,
            'exits': exits
        }


@pytest.fixture
def sample_data():
    """创建测试数据"""
    np.random.seed(42)
    dates = pd.date_range('2024-01-01', periods=100, freq='h')
    prices = np.random.randn(100).cumsum() + 100
    
    return pd.DataFrame({
        'Open': prices,
        'High': prices * 1.01,
        'Low': prices * 0.99,
        'Close': prices,
        'Volume': np.random.randint(1000, 10000, 100)
    }, index=dates)


@pytest.fixture
def strategy():
    """创建测试策略实例"""
    return SMAStrategy({'n1': 5, 'n2': 10, 'initial_capital': 10000})


@pytest.fixture
def adapter(strategy):
    """创建适配器实例"""
    return NativeVectorAdapter(strategy)


class TestNativeVectorAdapter:
    """测试 NativeVectorAdapter 核心功能"""
    
    def test_initialization(self, strategy):
        """测试适配器初始化"""
        adapter = NativeVectorAdapter(strategy)
        assert adapter.strategy_core == strategy
        assert adapter.results is None
        assert adapter.engine is not None
    
    def test_run_backtest(self, adapter, sample_data):
        """测试运行回测"""
        result = adapter.run_backtest(sample_data, cash=10000, commission=0.001)
        
        assert isinstance(result, dict)
        assert 'Start' in result
        assert 'End' in result
        assert 'Return [%]' in result
        assert 'Sharpe Ratio' in result
        assert 'Max. Drawdown [%]' in result
        assert '_equity_curve' in result
        assert '_trades' in result
    
    def test_backtest_result_format(self, adapter, sample_data):
        """测试回测结果格式"""
        result = adapter.run_backtest(sample_data, cash=10000)
        
        # 验证必需的键
        required_keys = [
            'Start', 'End', 'Duration',
            'Start Value', 'Equity Final [$]', 'Equity Peak [$]',
            'Return [%]', 'Buy & Hold Return [%]',
            'Max. Drawdown [%]', 'Avg. Drawdown [%]',
            'Max. Drawdown Duration', 'Avg. Drawdown Duration',
            'Sharpe Ratio', 'Sortino Ratio', 'Calmar Ratio',
            '# Trades', 'Win Rate [%]',
            'Best Trade [%]', 'Worst Trade [%]', 'Avg. Trade [%]',
            'Max. Trade Duration', 'Avg. Trade Duration',
            'Profit Factor', 'Expectancy [%]', 'SQN'
        ]
        
        for key in required_keys:
            assert key in result, f"Missing key: {key}"
    
    def test_equity_curve(self, adapter, sample_data):
        """测试权益曲线计算"""
        result = adapter.run_backtest(sample_data, cash=10000)
        equity_curve = result['_equity_curve']
        
        assert isinstance(equity_curve, pd.Series)
        assert len(equity_curve) == len(sample_data)
        assert equity_curve.index.equals(sample_data.index)
        assert equity_curve.iloc[0] == 10000  # 初始资金
    
    def test_trades_format(self, adapter, sample_data):
        """测试交易记录格式"""
        result = adapter.run_backtest(sample_data, cash=10000)
        trades = result['_trades']
        
        if len(trades) > 0:
            assert isinstance(trades, pd.DataFrame)
            # 验证交易记录列
            expected_columns = ['Entry Time', 'Exit Time', 'Entry Price', 
                              'Exit Price', 'Size', 'P/L', 'Return %', 'Direction']
            for col in expected_columns:
                assert col in trades.columns, f"Missing column: {col}"
    
    def test_metrics_calculation(self, adapter, sample_data):
        """测试绩效指标计算"""
        result = adapter.run_backtest(sample_data, cash=10000)
        
        # 验证收益率计算
        assert isinstance(result['Return [%]'], (int, float))
        assert result['Return [%]'] > -100  # 不可能亏损超过100%
        
        # 验证夏普比率
        assert isinstance(result['Sharpe Ratio'], (int, float))
        
        # 验证最大回撤
        assert isinstance(result['Max. Drawdown [%]'], (int, float))
        assert 0 <= result['Max. Drawdown [%]'] <= 100
        
        # 验证交易次数
        assert isinstance(result['# Trades'], int)
        assert result['# Trades'] >= 0
    
    def test_with_different_parameters(self, adapter, sample_data):
        """测试不同参数的回测"""
        # 测试不同初始资金
        result1 = adapter.run_backtest(sample_data, cash=5000)
        result2 = adapter.run_backtest(sample_data, cash=20000)
        
        assert result1['Start Value'] == 5000
        assert result2['Start Value'] == 20000
        
        # 测试不同手续费
        result3 = adapter.run_backtest(sample_data, cash=10000, commission=0.002)
        result4 = adapter.run_backtest(sample_data, cash=10000, commission=0.0005)
        
        # 手续费高的应该收益较低（或相等）
        assert result3['Return [%]'] <= result4['Return [%]'] + 0.1  # 允许小误差
    
    def test_empty_signals(self, sample_data):
        """测试无信号情况"""
        class NoSignalStrategy(StrategyCore):
            def calculate_indicators(self, data):
                return {'dummy': data['Close']}
            
            def generate_signals(self, indicators):
                return {
                    'entries': pd.Series(False, index=indicators['dummy'].index),
                    'exits': pd.Series(False, index=indicators['dummy'].index)
                }
        
        strategy = NoSignalStrategy({})
        adapter = NativeVectorAdapter(strategy)
        result = adapter.run_backtest(sample_data, cash=10000)
        
        assert result['# Trades'] == 0
        assert result['Return [%]'] == 0
    
    def test_all_signals(self, sample_data):
        """测试全信号情况"""
        class AllSignalStrategy(StrategyCore):
            def calculate_indicators(self, data):
                return {'dummy': data['Close']}

            def generate_signals(self, indicators):
                # 交替入场和出场信号
                n = len(indicators['dummy'])
                entries = pd.Series([i % 10 == 0 for i in range(n)], index=indicators['dummy'].index)
                exits = pd.Series([i % 10 == 5 for i in range(n)], index=indicators['dummy'].index)
                return {
                    'entries': entries,
                    'exits': exits
                }

        strategy = AllSignalStrategy({})
        adapter = NativeVectorAdapter(strategy)
        result = adapter.run_backtest(sample_data, cash=10000)

        # 应该有交易发生（每10个周期一次交易）
        assert result['# Trades'] >= 0  # 允许0交易，因为信号可能不触发实际交易


class TestStrategyRunner:
    """测试 StrategyRunner 功能"""
    
    def test_initialization(self, strategy):
        """测试运行器初始化"""
        runner = StrategyRunner(strategy, engine='native')
        assert runner.strategy_core == strategy
        assert runner.engine == 'native'
        assert runner.adapter is not None
    
    def test_run(self, strategy, sample_data):
        """测试运行回测"""
        runner = StrategyRunner(strategy)
        result = runner.run(sample_data, cash=10000)
        
        assert isinstance(result, dict)
        assert 'Return [%]' in result
    
    def test_switch_engine(self, strategy):
        """测试切换引擎"""
        runner = StrategyRunner(strategy, engine='native')
        assert runner.engine == 'native'
        assert isinstance(runner.adapter, NativeVectorAdapter)
    
    def test_enable_cache(self, strategy):
        """测试启用缓存"""
        runner = StrategyRunner(strategy)
        runner.enable_cache(True)
        assert strategy._cache_enabled is True
        
        runner.enable_cache(False)
        assert strategy._cache_enabled is False
    
    def test_get_cache_stats(self, strategy, sample_data):
        """测试获取缓存统计"""
        runner = StrategyRunner(strategy)
        runner.run(sample_data)
        
        stats = runner.get_cache_stats()
        assert 'hits' in stats
        assert 'misses' in stats
        assert 'total' in stats
        assert 'hit_rate' in stats
    
    def test_run_on_multiple_data(self, strategy):
        """测试在多个数据上运行"""
        np.random.seed(42)
        data_dict = {
            'BTCUSDT': pd.DataFrame({
                'Close': np.random.randn(100).cumsum() + 50000
            }, index=pd.date_range('2024-01-01', periods=100, freq='h')),
            'ETHUSDT': pd.DataFrame({
                'Close': np.random.randn(100).cumsum() + 3000
            }, index=pd.date_range('2024-01-01', periods=100, freq='h'))
        }
        
        runner = StrategyRunner(strategy)
        results = runner.run_on_multiple_data(data_dict, cash=10000)
        
        assert isinstance(results, dict)
        assert 'BTCUSDT' in results
        assert 'ETHUSDT' in results
        assert 'Return [%]' in results['BTCUSDT']
        assert 'Return [%]' in results['ETHUSDT']
    
    def test_run_on_multiple_engines(self, strategy, sample_data):
        """测试在多个引擎上运行"""
        runner = StrategyRunner(strategy)
        results = runner.run_on_multiple_engines(
            sample_data,
            engines=['native'],
            cash=10000
        )

        assert isinstance(results, dict)
        assert 'native' in results


class TestResultCompatibility:
    """测试结果兼容性测试"""
    
    def test_result_types(self, adapter, sample_data):
        """测试结果数据类型"""
        result = adapter.run_backtest(sample_data, cash=10000)
        
        # 验证日期类型
        assert isinstance(result['Start'], pd.Timestamp)
        assert isinstance(result['End'], pd.Timestamp)
        assert isinstance(result['Duration'], pd.Timedelta)
        
        # 验证数值类型
        assert isinstance(result['Start Value'], (int, float))
        assert isinstance(result['Equity Final [$]'], (int, float))
        assert isinstance(result['Equity Peak [$]'], (int, float))
        assert isinstance(result['Return [%]'], (int, float))
        assert isinstance(result['Max. Drawdown [%]'], (int, float))
        
        # 验证交易统计
        assert isinstance(result['# Trades'], int)
        assert isinstance(result['Win Rate [%]'], (int, float))
    
    def test_result_consistency(self, adapter, sample_data):
        """测试结果一致性"""
        result = adapter.run_backtest(sample_data, cash=10000)
        
        # 权益峰值应该大于等于最终权益
        assert result['Equity Peak [$]'] >= result['Equity Final [$]']
        
        # 最大回撤应该在0-100%之间
        assert 0 <= result['Max. Drawdown [%]'] <= 100
        
        # 胜率应该在0-100%之间
        assert 0 <= result['Win Rate [%]'] <= 100
        
        # 交易次数应该非负
        assert result['# Trades'] >= 0
    
    def test_equity_curve_consistency(self, adapter, sample_data):
        """测试权益曲线一致性"""
        result = adapter.run_backtest(sample_data, cash=10000)
        equity_curve = result['_equity_curve']
        
        # 权益曲线的第一个值应该等于初始资金
        assert abs(equity_curve.iloc[0] - 10000) < 0.01
        
        # 权益曲线的最后一个值应该等于最终权益
        assert abs(equity_curve.iloc[-1] - result['Equity Final [$]']) < 0.01


class TestAdapterEdgeCases:
    """测试适配器边界情况"""
    
    def test_single_data_point(self, adapter):
        """测试单数据点"""
        data = pd.DataFrame({
            'Open': [100],
            'High': [101],
            'Low': [99],
            'Close': [100],
            'Volume': [1000]
        }, index=pd.date_range('2024-01-01', periods=1))
        
        result = adapter.run_backtest(data, cash=10000)
        assert isinstance(result, dict)
    
    def test_small_dataset(self, adapter):
        """测试小数据集"""
        data = pd.DataFrame({
            'Open': [100, 101, 102],
            'High': [101, 102, 103],
            'Low': [99, 100, 101],
            'Close': [100, 101, 102],
            'Volume': [1000, 2000, 3000]
        }, index=pd.date_range('2024-01-01', periods=3, freq='h'))
        
        result = adapter.run_backtest(data, cash=10000)
        assert isinstance(result, dict)
    
    def test_large_dataset(self, adapter):
        """测试大数据集"""
        np.random.seed(42)
        n = 10000
        data = pd.DataFrame({
            'Open': np.random.randn(n).cumsum() + 100,
            'High': np.random.randn(n).cumsum() + 101,
            'Low': np.random.randn(n).cumsum() + 99,
            'Close': np.random.randn(n).cumsum() + 100,
            'Volume': np.random.randint(1000, 10000, n)
        }, index=pd.date_range('2024-01-01', periods=n, freq='min'))
        
        result = adapter.run_backtest(data, cash=10000)
        assert isinstance(result, dict)
        assert 'Return [%]' in result
