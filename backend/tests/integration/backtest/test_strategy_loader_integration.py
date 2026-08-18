"""策略加载集成测试 — 覆盖完整回测流程

测试场景：
1. 策略文件查找（多目录优先级）
2. 策略类识别（排除抽象基类）
3. 策略实例化（Config 传递、参数过滤）
4. 端到端回测执行
"""

import pytest

from backtest.strategy_loader_service import StrategyLoadError, StrategyLoaderService


class TestStrategyLoaderIntegration:
    """策略加载集成测试"""

    def test_load_strategy_dual_ma(self):
        """测试加载双均线策略"""
        strategy = StrategyLoaderService.load_strategy(
            "dual_ma",
            strategy_params={"fast": 10, "slow": 30},
            instrument_ids=[{"symbol": "BTCUSDT", "venue": "BINANCE"}],
            bar_types=["1h"],
        )
        assert strategy is not None
        assert strategy.__class__.__name__ == "DualMA"
        assert strategy.config.name == "DualMA"
        assert strategy.config.params == {"fast": 10, "slow": 30}

    def test_load_strategy_with_params(self):
        """测试加载策略时传递自定义参数"""
        strategy = StrategyLoaderService.load_strategy(
            "dual_ma",
            strategy_params={"fast": 5, "slow": 20, "position_limit": 0.2},
            instrument_ids=[{"symbol": "ETHUSDT", "venue": "BINANCE"}],
            bar_types=["15m"],
        )
        assert strategy is not None
        assert strategy.config.params == {"fast": 5, "slow": 20, "position_limit": 0.2}
        # symbol 从 instrument_ids 中提取
        assert strategy.config.symbol == "ETHUSDT"

    def test_load_strategy_invalid_name(self):
        """测试加载不存在的策略"""
        with pytest.raises(StrategyLoadError, match="策略文件不存在"):
            StrategyLoaderService.load_strategy(
                "non_existent_strategy",
                strategy_params={},
                instrument_ids=[{"symbol": "BTCUSDT", "venue": "BINANCE"}],
                bar_types=["1h"],
            )

    def test_load_strategy_missing_instrument_ids(self):
        """测试缺少 instrument_ids 参数"""
        with pytest.raises(StrategyLoadError, match="需要传入 instrument_ids"):
            StrategyLoaderService.load_strategy("dual_ma", strategy_params={}, instrument_ids=None, bar_types=["1h"])

    def test_load_strategy_empty_instrument_ids(self):
        """测试空的 instrument_ids 参数"""
        with pytest.raises(StrategyLoadError, match="instrument_ids 和 bar_types 非空"):
            StrategyLoaderService.load_strategy("dual_ma", strategy_params={}, instrument_ids=[], bar_types=["1h"])

    def test_find_strategy_class_excludes_abstract(self):
        """测试策略类查找排除抽象基类"""
        # 加载 dual_ma 模块
        strategy_file = StrategyLoaderService._find_strategy_file("dual_ma")
        assert strategy_file is not None

        # 导入模块
        import importlib
        import sys

        strategies_dir = strategy_file.parent
        if str(strategies_dir) not in sys.path:
            sys.path.insert(0, str(strategies_dir))

        if "dual_ma" in sys.modules:
            del sys.modules["dual_ma"]

        module = importlib.import_module("dual_ma")

        # 查找策略类
        strategy_class = StrategyLoaderService._find_strategy_class(module)

        # 应该找到 DualMA，而不是 BaseStrategy（抽象基类）
        assert strategy_class is not None
        assert strategy_class.__name__ == "DualMA"

    def test_find_strategy_file_priority(self):
        """测试策略文件查找优先级"""
        # 验证策略目录按优先级排序
        dirs = StrategyLoaderService._get_strategies_dirs()
        assert len(dirs) > 0

        # 验证优先顺序：templates > example/strategies > strategies
        paths = [d.name for d in dirs]
        if "templates" in paths:
            assert paths.index("templates") < paths.index("strategies") if "strategies" in paths else True

    def test_get_source_data_dir_import(self):
        """测试 get_source_data_dir 导入路径"""
        from cli.data import get_source_data_dir

        assert callable(get_source_data_dir)
        assert get_source_data_dir().exists()

    def test_load_multiple_strategies(self):
        """测试加载多个不同类型的策略"""
        strategies_to_test = ["dual_ma", "trend_follow", "momentum", "grid"]

        for strategy_name in strategies_to_test:
            try:
                strategy = StrategyLoaderService.load_strategy(
                    strategy_name,
                    strategy_params={},
                    instrument_ids=[{"symbol": "BTCUSDT", "venue": "BINANCE"}],
                    bar_types=["1h"],
                )
                assert strategy is not None
                # 策略类名应该不是 BaseStrategy
                assert strategy.__class__.__name__ != "BaseStrategy"
            except StrategyLoadError as e:
                # 如果策略文件不存在，跳过
                if "策略文件不存在" in str(e):
                    continue
                raise

    def test_strategy_config_inheritance(self):
        """测试策略配置类继承"""
        strategy = StrategyLoaderService.load_strategy(
            "dual_ma",
            strategy_params={},
            instrument_ids=[{"symbol": "BTCUSDT", "venue": "BINANCE"}],
            bar_types=["1h"],
        )
        assert strategy is not None

        # 获取策略的 config（处理可能的包装器）
        config = getattr(strategy, "config", None)
        if config is None and hasattr(strategy, "_strategy"):
            config = getattr(strategy._strategy, "config", None)

        assert config is not None, f"策略对象缺少 config 属性，可用属性: {dir(strategy)}"
        assert hasattr(config, "name")
        assert hasattr(config, "symbol")
        assert hasattr(config, "params")
        assert hasattr(config, "position_limit")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
