"""
StrategyCore 单元测试
测试策略核心类的功能和接口
"""

import pytest
import pandas as pd
import numpy as np
from strategy.core import StrategyCore


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
    return SMAStrategy({
        'n1': 5,
        'n2': 10,
        'initial_capital': 10000
    })


class TestStrategyCore:
    """测试 StrategyCore 核心功能"""
    
    def test_initialization(self, strategy):
        """测试策略初始化"""
        assert strategy.params['n1'] == 5
        assert strategy.params['n2'] == 10
        assert strategy.params['initial_capital'] == 10000
        assert strategy.indicators == {}
        assert strategy._cache_enabled is True
    
    def test_run(self, strategy, sample_data):
        """测试策略运行"""
        result = strategy.run(sample_data)
        
        assert 'indicators' in result
        assert 'signals' in result
        assert 'sma5' in result['indicators']
        assert 'sma10' in result['indicators']
        assert 'entries' in result['signals']
        assert 'exits' in result['signals']
    
    def test_calculate_indicators(self, strategy, sample_data):
        """测试指标计算"""
        indicators = strategy.calculate_indicators(sample_data)
        
        assert 'sma5' in indicators
        assert 'sma10' in indicators
        assert len(indicators['sma5']) == len(sample_data)
        assert len(indicators['sma10']) == len(sample_data)
    
    def test_generate_signals(self, strategy, sample_data):
        """测试信号生成"""
        indicators = strategy.calculate_indicators(sample_data)
        signals = strategy.generate_signals(indicators)
        
        assert 'entries' in signals
        assert 'exits' in signals
        assert isinstance(signals['entries'], pd.Series)
        assert isinstance(signals['exits'], pd.Series)
        assert signals['entries'].dtype == bool
        assert signals['exits'].dtype == bool
    
    def test_generate_long_signals(self, strategy, sample_data):
        """测试多头信号生成"""
        indicators = strategy.calculate_indicators(sample_data)
        long_entries, long_exits = strategy.generate_long_signals(indicators)
        
        assert isinstance(long_entries, pd.Series)
        assert isinstance(long_exits, pd.Series)
        assert long_entries.dtype == bool
        assert long_exits.dtype == bool
    
    def test_generate_short_signals(self, strategy, sample_data):
        """测试空头信号生成"""
        indicators = strategy.calculate_indicators(sample_data)
        short_entries, short_exits = strategy.generate_short_signals(indicators)
        
        assert isinstance(short_entries, pd.Series)
        assert isinstance(short_exits, pd.Series)
        assert short_entries.dtype == bool
        assert short_exits.dtype == bool
    
    def test_cache_mechanism(self, strategy, sample_data):
        """测试缓存机制"""
        # 第一次运行
        result1 = strategy.run(sample_data)
        stats1 = strategy.get_cache_stats()
        
        # 第二次运行（应该命中缓存）
        result2 = strategy.run(sample_data)
        stats2 = strategy.get_cache_stats()
        
        assert stats2['hits'] > stats1['hits']
        assert stats2['hit_rate'] > 0
    
    def test_enable_disable_cache(self, strategy):
        """测试启用/禁用缓存"""
        strategy.enable_cache(False)
        assert strategy._cache_enabled is False
        
        strategy.enable_cache(True)
        assert strategy._cache_enabled is True
    
    def test_clear_cache(self, strategy, sample_data):
        """测试清除缓存"""
        strategy.run(sample_data)
        assert len(strategy._indicator_cache) > 0
        
        strategy.clear_cache()
        assert len(strategy._indicator_cache) == 0
        assert strategy._cache_hits == 0
        assert strategy._cache_misses == 0
    
    def test_get_cache_stats(self, strategy, sample_data):
        """测试获取缓存统计"""
        stats = strategy.get_cache_stats()
        assert 'hits' in stats
        assert 'misses' in stats
        assert 'total' in stats
        assert 'hit_rate' in stats
        
        # 运行策略后再次检查
        strategy.run(sample_data)
        stats = strategy.get_cache_stats()
        assert stats['total'] > 0
    
    def test_preprocess_data(self, strategy, sample_data):
        """测试数据预处理"""
        processed = strategy.preprocess_data(sample_data)
        assert isinstance(processed, pd.DataFrame)
        assert len(processed) == len(sample_data)
    
    def test_filter_signals(self, strategy, sample_data):
        """测试信号过滤"""
        indicators = strategy.calculate_indicators(sample_data)
        signals = strategy.generate_signals(indicators)
        filtered = strategy.filter_signals(sample_data, signals, indicators)
        
        assert isinstance(filtered, dict)
        assert 'entries' in filtered
        assert 'exits' in filtered
    
    def test_postprocess_signals(self, strategy, sample_data):
        """测试信号后处理"""
        indicators = strategy.calculate_indicators(sample_data)
        signals = strategy.generate_signals(indicators)
        processed = strategy.postprocess_signals(sample_data, signals, indicators)
        
        assert isinstance(processed, dict)
        assert 'entries' in processed
        assert 'exits' in processed
    
    def test_calculate_position_size(self, strategy, sample_data):
        """测试仓位大小计算"""
        indicators = strategy.calculate_indicators(sample_data)
        signals = strategy.generate_signals(indicators)
        sizes = strategy.calculate_position_size(
            sample_data, signals, indicators, 10000
        )
        
        assert isinstance(sizes, pd.Series)
        assert len(sizes) == len(sample_data)
    
    def test_calculate_long_position_size(self, strategy, sample_data):
        """测试多头仓位大小计算"""
        indicators = strategy.calculate_indicators(sample_data)
        signals = strategy.generate_signals(indicators)
        sizes = strategy.calculate_long_position_size(
            sample_data, signals, indicators, 10000
        )
        
        assert isinstance(sizes, pd.Series)
        assert len(sizes) == len(sample_data)
    
    def test_calculate_short_position_size(self, strategy, sample_data):
        """测试空头仓位大小计算"""
        indicators = strategy.calculate_indicators(sample_data)
        signals = strategy.generate_signals(indicators)
        sizes = strategy.calculate_short_position_size(
            sample_data, signals, indicators, 10000
        )
        
        assert isinstance(sizes, pd.Series)
        assert len(sizes) == len(sample_data)
    
    def test_generate_stop_loss_take_profit(self, strategy, sample_data):
        """测试止损止盈信号生成"""
        indicators = strategy.calculate_indicators(sample_data)
        signals = strategy.generate_signals(indicators)
        sl_tp = strategy.generate_stop_loss_take_profit(sample_data, signals, indicators)
        
        assert isinstance(sl_tp, dict)
        assert 'stop_loss' in sl_tp
        assert 'take_profit' in sl_tp
        assert isinstance(sl_tp['stop_loss'], pd.Series)
        assert isinstance(sl_tp['take_profit'], pd.Series)


class TestStrategyCoreMultiAsset:
    """测试多资产策略功能"""
    
    def test_run_multiple(self, strategy):
        """测试多资产运行"""
        np.random.seed(42)
        data_dict = {
            'BTCUSDT': pd.DataFrame({
                'Close': np.random.randn(100).cumsum() + 50000
            }, index=pd.date_range('2024-01-01', periods=100, freq='h')),
            'ETHUSDT': pd.DataFrame({
                'Close': np.random.randn(100).cumsum() + 3000
            }, index=pd.date_range('2024-01-01', periods=100, freq='h'))
        }
        
        results = strategy.run_multiple(data_dict)
        
        assert isinstance(results, dict)
        assert 'BTCUSDT' in results
        assert 'ETHUSDT' in results
        assert 'indicators' in results['BTCUSDT']
        assert 'signals' in results['BTCUSDT']
    
    def test_preprocess_multiple_data(self, strategy):
        """测试多资产数据预处理"""
        data_dict = {
            'BTCUSDT': pd.DataFrame({'Close': [100, 101, 102]}),
            'ETHUSDT': pd.DataFrame({'Close': [50, 51, 52]})
        }
        
        processed = strategy.preprocess_multiple_data(data_dict)
        
        assert isinstance(processed, dict)
        assert 'BTCUSDT' in processed
        assert 'ETHUSDT' in processed
    
    def test_coordinate_multiple_assets(self, strategy):
        """测试多资产协调"""
        data_dict = {
            'BTCUSDT': pd.DataFrame({'Close': [100, 101, 102]}),
            'ETHUSDT': pd.DataFrame({'Close': [50, 51, 52]})
        }
        results_dict = {
            'BTCUSDT': {'indicators': {}, 'signals': {}},
            'ETHUSDT': {'indicators': {}, 'signals': {}}
        }
        
        coordinated = strategy.coordinate_multiple_assets(results_dict, data_dict)
        
        assert isinstance(coordinated, dict)
        assert 'BTCUSDT' in coordinated
        assert 'ETHUSDT' in coordinated


class TestStrategyCoreCustomIndicators:
    """测试自定义指标功能"""
    
    def test_register_indicator(self, strategy):
        """测试注册自定义指标"""
        def custom_indicator(data, period=5):
            return data['Close'].rolling(window=period).std()
        
        strategy.register_indicator('volatility', custom_indicator)
        assert 'volatility' in strategy.custom_indicators
    
    def test_calculate_custom_indicator(self, strategy, sample_data):
        """测试计算自定义指标"""
        def custom_indicator(data, period=5):
            return data['Close'].rolling(window=period).std()
        
        strategy.register_indicator('volatility', custom_indicator)
        result = strategy.calculate_custom_indicator('volatility', sample_data, period=5)
        
        assert isinstance(result, pd.Series)
        assert len(result) == len(sample_data)
    
    def test_calculate_custom_indicator_not_found(self, strategy, sample_data):
        """测试计算未注册的自定义指标"""
        with pytest.raises(ValueError, match="Custom indicator 'unknown' not registered"):
            strategy.calculate_custom_indicator('unknown', sample_data)
