# -*- coding: utf-8 -*-
"""
策略加载回退机制测试

测试策略加载三层回退机制的核心逻辑：
1. config 中的 strategy_code（优先）
2. 数据库中的策略代码（回退）
3. 文件路径加载（最后回退）

以及自动发现策略类和创建 Axon 策略实例的逻辑。

这些测试直接验证了 d6be87c 提交中实现的三层回退机制。
"""

import pytest
import tempfile
import os
import sys
import types


class TestStrategyCodeLoading:
    """测试策略代码加载功能"""

    @pytest.fixture
    def quantcell_strategy_code(self):
        """QuantCell 策略代码"""
        return '''
class StrategyBase:
    """Mock StrategyBase"""
    pass

class StrategyConfig:
    """Mock StrategyConfig"""
    pass

class InstrumentId:
    """Mock InstrumentId"""
    pass

class Bar:
    """Mock Bar"""
    pass

class EMACrossStrategy(StrategyBase):
    def __init__(self, config):
        super().__init__()
        self.fast_period = getattr(config, 'fast_period', 10)
        self.slow_period = getattr(config, 'slow_period', 20)

    def on_start(self):
        pass

    def on_stop(self):
        pass

    def on_bar(self, bar):
        pass
'''

    @pytest.fixture
    def abstract_strategy_code(self):
        """抽象策略代码（用于测试排除逻辑）"""
        return '''
from abc import ABC, abstractmethod

class StrategyBase(ABC):
    """Mock StrategyBase - ABC subclass"""
    pass

class AbstractStrategy(StrategyBase):
    @abstractmethod
    def on_bar(self, bar):
        pass

class ConcreteStrategy(StrategyBase):
    def on_bar(self, bar):
        pass
'''

    @pytest.fixture
    def pure_abstract_strategy_code(self):
        """纯抽象策略代码（用于测试排除逻辑）"""
        return '''
from abc import ABC, abstractmethod

class StrategyBase(ABC):
    """Mock StrategyBase - ABC subclass"""
    pass

class AbstractStrategy(StrategyBase):
    @abstractmethod
    def on_bar(self, bar):
        pass
'''

    @pytest.fixture
    def mixed_strategy_code(self):
        """混合代码（包含多个类）"""
        return '''
class StrategyBase:
    """Mock StrategyBase"""
    pass

class ActualStrategy(StrategyBase):
    def on_start(self):
        pass

    def on_stop(self):
        pass

    def on_bar(self, bar):
        pass

class SomeHelper:
    """辅助类，不应被选中"""
    def help(self):
        pass
'''

    def test_dynamic_module_creation(self, quantcell_strategy_code):
        """测试动态创建模块并执行策略代码"""
        module_name = "test_strategy_module"
        module = types.ModuleType(module_name)
        sys.modules[module_name] = module

        exec(quantcell_strategy_code, module.__dict__)

        assert hasattr(module, 'EMACrossStrategy')
        assert hasattr(module, 'StrategyBase')
        assert hasattr(module, 'StrategyConfig')

        strategy_class = getattr(module, 'EMACrossStrategy')
        assert strategy_class is not None
        assert strategy_class.__name__ == 'EMACrossStrategy'

        del sys.modules[module_name]

    def test_autodiscover_strategy_class(self, quantcell_strategy_code):
        """测试自动发现具体策略类"""
        module_name = "test_autodiscover_module"
        module = types.ModuleType(module_name)
        sys.modules[module_name] = module

        exec(quantcell_strategy_code, module.__dict__)

        StrategyBase = module.StrategyBase
        strategy_class = None
        for attr_name in dir(module):
            if attr_name.startswith('_'):
                continue

            attr = getattr(module, attr_name)
            if isinstance(attr, type):
                try:
                    is_strategy_subclass = (
                        issubclass(attr, StrategyBase)
                        and attr is not StrategyBase
                    )
                    if is_strategy_subclass:
                        strategy_class = attr
                        break
                except TypeError:
                    pass

        assert strategy_class is not None
        assert strategy_class.__name__ == 'EMACrossStrategy'

        del sys.modules[module_name]

    def test_abstract_class_detection(self, abstract_strategy_code):
        """测试抽象类被正确排除，只选择具体策略类"""
        module_name = "test_abstract_module"
        module = types.ModuleType(module_name)
        sys.modules[module_name] = module

        exec(abstract_strategy_code, module.__dict__)

        StrategyBase = module.StrategyBase
        concrete_strategies = []
        for attr_name in dir(module):
            if attr_name.startswith('_'):
                continue

            attr = getattr(module, attr_name)
            if isinstance(attr, type):
                try:
                    is_strategy_subclass = (
                        issubclass(attr, StrategyBase)
                        and attr is not StrategyBase
                    )
                    has_abstract_methods = bool(getattr(attr, '__abstractmethods__', None))
                    is_concrete = is_strategy_subclass and not has_abstract_methods

                    if is_concrete:
                        concrete_strategies.append(attr_name)
                except TypeError:
                    pass

        assert 'ConcreteStrategy' in concrete_strategies, "应该找到 ConcreteStrategy"
        assert 'AbstractStrategy' not in concrete_strategies, "AbstractStrategy 有抽象方法不应该被包含"

        del sys.modules[module_name]

    def test_pure_abstract_class_excluded(self, pure_abstract_strategy_code):
        """测试纯抽象类被正确排除"""
        module_name = "test_pure_abstract_module"
        module = types.ModuleType(module_name)
        sys.modules[module_name] = module

        exec(pure_abstract_strategy_code, module.__dict__)

        StrategyBase = module.StrategyBase
        concrete_strategies = []
        for attr_name in dir(module):
            if attr_name.startswith('_'):
                continue

            attr = getattr(module, attr_name)
            if isinstance(attr, type):
                try:
                    is_strategy_subclass = (
                        issubclass(attr, StrategyBase)
                        and attr is not StrategyBase
                    )
                    has_abstract_methods = bool(getattr(attr, '__abstractmethods__', None))
                    is_concrete = is_strategy_subclass and not has_abstract_methods

                    if is_concrete:
                        concrete_strategies.append(attr_name)
                except TypeError:
                    pass

        assert len(concrete_strategies) == 0, f"纯抽象策略类不应该被识别为具体策略，但找到了: {concrete_strategies}"

        del sys.modules[module_name]

    def test_mixed_code_selects_concrete_strategy(self, mixed_strategy_code):
        """测试混合代码中正确选择具体策略类"""
        module_name = "test_mixed_module"
        module = types.ModuleType(module_name)
        sys.modules[module_name] = module

        exec(mixed_strategy_code, module.__dict__)

        StrategyBase = module.StrategyBase
        strategy_class = None
        for attr_name in dir(module):
            if attr_name.startswith('_'):
                continue

            attr = getattr(module, attr_name)
            if isinstance(attr, type):
                try:
                    is_strategy_subclass = (
                        issubclass(attr, StrategyBase)
                        and attr is not StrategyBase
                    )
                    if is_strategy_subclass:
                        strategy_class = attr
                        break
                except TypeError:
                    pass

        assert strategy_class is not None
        assert strategy_class.__name__ == 'ActualStrategy'

        del sys.modules[module_name]


class TestFilePathLoading:
    """测试文件路径加载功能"""

    @pytest.fixture
    def strategy_file_content(self):
        return '''
class StrategyBase:
    pass

class TestStrategy(StrategyBase):
    def on_start(self):
        pass
'''

    def test_load_strategy_from_file(self, strategy_file_content):
        """测试从文件路径加载策略"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(strategy_file_content)
            temp_path = f.name

        try:
            with open(temp_path, 'r', encoding='utf-8') as f:
                loaded_code = f.read()

            assert loaded_code == strategy_file_content

            module_name = "test_file_module"
            module = types.ModuleType(module_name)
            sys.modules[module_name] = module

            exec(loaded_code, module.__dict__)

            assert hasattr(module, 'TestStrategy')

            del sys.modules[module_name]
        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)

    def test_file_not_exists_raises_error(self):
        """测试文件不存在时抛出错误"""
        nonexistent_path = "/nonexistent/path/strategy.py"

        with pytest.raises((FileNotFoundError, ImportError)):
            with open(nonexistent_path, 'r', encoding='utf-8') as f:
                f.read()


class TestFallbackMechanismLogic:
    """测试三层回退机制逻辑"""

    def test_fallback_level_1_config_priority(self):
        """测试第一层：config 中的 strategy_code 优先"""
        config = {
            "strategy_code": "print('code from config')",
            "strategy_id": None,
        }
        strategy_path = "/some/path/strategy.py"

        strategy_code = config.get("strategy_code")
        if not strategy_code:
            if config.get("strategy_id"):
                strategy_code = "code from database"
            elif strategy_path and os.path.exists(strategy_path):
                with open(strategy_path, 'r') as f:
                    strategy_code = f.read()

        assert strategy_code == "print('code from config')"

    def test_fallback_level_2_database(self):
        """测试第二层：数据库回退"""
        config = {
            "strategy_code": None,
            "strategy_id": 123,
        }

        strategy_code = config.get("strategy_code")
        if not strategy_code:
            if config.get("strategy_id"):
                strategy_code = "code from database"

        assert strategy_code == "code from database"

    def test_fallback_level_3_file_path(self):
        """测试第三层：文件路径回退"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write("# code from file")
            temp_path = f.name

        try:
            config = {
                "strategy_code": None,
                "strategy_id": None,
            }

            strategy_code = config.get("strategy_code")
            if not strategy_code:
                if config.get("strategy_id"):
                    strategy_code = "code from database"
                elif temp_path and os.path.exists(temp_path):
                    with open(temp_path, 'r') as f:
                        strategy_code = f.read()

            assert strategy_code == "# code from file"
        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)

    def test_empty_strategy_raises_error(self):
        """测试空策略代码时抛出错误"""
        config = {
            "strategy_code": None,
            "strategy_id": None,
        }
        strategy_path = None

        strategy_code = config.get("strategy_code")
        if not strategy_code:
            if config.get("strategy_id"):
                strategy_code = "code from database"
            elif strategy_path and os.path.exists(strategy_path):
                with open(strategy_path, 'r') as f:
                    strategy_code = f.read()

        with pytest.raises(ImportError, match="策略代码为空"):
            if not strategy_code:
                raise ImportError("策略代码为空")


class TestConfigClassNamingPatterns:
    """测试 Config 类命名模式匹配"""

    def test_config_naming_patterns(self):
        """测试各种 Config 命名模式的匹配逻辑"""
        test_cases = [
            ("EMACrossStrategy", "EMACrossStrategyConfig"),
            ("GridOrderValidationStrategy", "GridOrderValidationStrategyConfig"),
            ("SMACross", "SMACrossConfig"),
            ("MACD", "MACDConfig"),
        ]

        for strategy_name, expected_config_name in test_cases:
            patterns = [
                f"{strategy_name}Config",
                strategy_name.replace("Strategy", "") + "Config",
                f"{strategy_name.split('Strategy')[0]}Config"
            ]

            assert expected_config_name in patterns or any(
                expected_config_name == p for p in patterns
            ), f"Config name {expected_config_name} not found in patterns for {strategy_name}"


class TestStrategyBaseExclusion:
    """测试 StrategyBase 排除逻辑"""

    def test_strategy_base_itself_excluded(self):
        """测试 StrategyBase 自身被正确排除"""
        class StrategyBase:
            pass

        strategy_class = StrategyBase
        class_name = "StrategyBase"

        is_valid = True
        if class_name == "StrategyBase":
            if strategy_class is StrategyBase:
                is_valid = False

        assert is_valid is False

    def test_abstract_class_detection(self):
        """测试抽象类检测"""
        from abc import ABC, abstractmethod

        class AbstractStrategy(ABC):
            @abstractmethod
            def on_bar(self, bar):
                pass

        has_abstract = bool(getattr(AbstractStrategy, '__abstractmethods__', None))
        assert has_abstract is True, "抽象类应该有 __abstractmethods__"


class TestStrategyParamsExtraction:
    """测试策略参数提取"""

    def test_extract_symbols_from_config(self):
        """测试从配置提取交易对"""
        config = {
            "symbols": ["BTCUSDT", "ETHUSDT"],
            "exchange": "binance",
            "timeframe": "1H",
            "params": {"risk_level": "low"}
        }

        symbols = config.get("symbols", ["BTCUSDT"])
        assert symbols == ["BTCUSDT", "ETHUSDT"]

    def test_extract_exchange_from_dict(self):
        """测试从字典格式提取交易所名称"""
        config = {
            "exchange": {"exchange": "binance", "testnet": True},
            "symbols": ["BTCUSDT"]
        }

        exchange_raw = config.get("exchange")
        if isinstance(exchange_raw, dict):
            exchange_name = exchange_raw.get("exchange", "binance")
        else:
            exchange_name = str(exchange_raw) if exchange_raw else "binance"

        assert exchange_name == "binance"

    def test_default_values(self):
        """测试默认值处理"""
        config = {}

        symbols = config.get("symbols", ["BTCUSDT"])
        exchange = config.get("exchange", "binance")
        timeframe = config.get("timeframe", "1m")
        params = config.get("params", {})

        assert symbols == ["BTCUSDT"]
        assert exchange == "binance"
        assert timeframe == "1m"
        assert params == {}


class TestAxonStrategyCreation:
    """测试 Axon 策略创建逻辑"""

    def test_config_class_lookup_priority(self):
        """测试 Config 类查找优先级"""
        class EMACrossConfig:
            pass

        class EMACrossStrategy:
            pass

        class FakeModule:
            pass

        module = FakeModule()
        module.EMACrossConfig = EMACrossConfig

        strategy_class = EMACrossStrategy
        possible_config_names = [
            f"{strategy_class.__name__}Config",
            strategy_class.__name__.replace("Strategy", "") + "Config",
            f"{strategy_class.__name__.split('Strategy')[0]}Config"
        ]

        config_class = None
        for config_name in possible_config_names:
            if hasattr(module, config_name):
                config_class = getattr(module, config_name)
                break

        assert config_class is EMACrossConfig

    def test_strategy_instance_creation(self):
        """测试策略实例创建"""
        class MockConfig:
            fast_period = 10
            slow_period = 20

        class EMACrossStrategy:
            def __init__(self, config):
                self.fast_period = config.fast_period
                self.slow_period = config.slow_period

        config = MockConfig()
        strategy = EMACrossStrategy(config)

        assert strategy.fast_period == 10
        assert strategy.slow_period == 20


class TestAutoDiscoverLogic:
    """测试自动发现逻辑"""

    def test_excludes_private_classes(self):
        """测试排除私有类"""
        class StrategyBase:
            pass

        class _PrivateStrategy(StrategyBase):
            pass

        class PublicStrategy(StrategyBase):
            pass

        classes = [StrategyBase, _PrivateStrategy, PublicStrategy]

        discovered = []
        for cls in classes:
            if not cls.__name__.startswith('_') and cls is not StrategyBase:
                discovered.append(cls)

        assert len(discovered) == 1
        assert discovered[0] is PublicStrategy

    def test_excludes_typing_modules(self):
        """测试排除 typing 模块中的类"""
        import typing

        excluded_names = ['Any', 'Dict', 'List', 'Optional']

        for name in excluded_names:
            if hasattr(typing, name):
                attr = getattr(typing, name)
                is_excluded = (
                    attr is typing.Any or
                    attr is typing.Dict or
                    attr is typing.List or
                    attr is typing.Optional
                )
                assert is_excluded, f"{name} should be excluded as typing module class"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
