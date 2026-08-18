"""
策略AST解析器单元测试

测试新的统一AST解析工具的功能。
"""

import pytest

from utils.strategy_ast_parser import (
    StrategyASTParser,
    StrategyClassInfo,
    parse_strategy_code,
)


class TestStrategyASTParser:
    """StrategyASTParser 测试类"""

    def setup_method(self):
        """测试前准备"""
        self.parser = StrategyASTParser()

    def test_parse_valid_code(self):
        """测试解析有效代码"""
        code = """
class MyStrategy:
    def __init__(self):
        self.param = 10
"""
        tree = self.parser.parse(code)
        assert tree is not None

    def test_parse_invalid_code(self):
        """测试解析无效代码"""
        code = "def foo(:  # 语法错误"
        tree = self.parser.parse(code)
        assert tree is None

    def test_find_all_classes(self):
        """测试查找所有类"""
        code = """
class Config:
    pass

class MyStrategy:
    pass
"""
        tree = self.parser.parse(code)
        classes = self.parser.find_all_classes(tree)

        assert len(classes) == 2
        assert classes[0].class_name == "Config"
        assert classes[0].is_config_class is True
        assert classes[1].class_name == "MyStrategy"
        assert classes[1].is_strategy_class is True

    def test_find_strategy_classes(self):
        """测试查找策略类"""
        code = """
class Config:
    pass

class MyStrategy(StrategyBase):
    def on_bar(self):
        pass
"""
        tree = self.parser.parse(code)
        strategy_classes = self.parser.find_strategy_classes(tree)

        assert len(strategy_classes) == 1
        assert strategy_classes[0].class_name == "MyStrategy"
        assert strategy_classes[0].is_strategy_class is True
        assert "StrategyBase" in strategy_classes[0].base_classes

    def test_find_config_classes(self):
        """测试查找配置类"""
        code = """
class MyStrategyConfig:
    pass

class MyStrategy:
    pass
"""
        tree = self.parser.parse(code)
        config_classes = self.parser.find_config_classes(tree)

        assert len(config_classes) == 1
        assert config_classes[0].class_name == "MyStrategyConfig"
        assert config_classes[0].is_config_class is True

    def test_find_imports(self):
        """测试查找导入"""
        code = """
import os
from datetime import datetime
from strategy.core import StrategyBase
"""
        tree = self.parser.parse(code)
        imports = self.parser.find_imports(tree)

        assert "os" in imports
        assert "datetime" in imports
        assert "strategy.core" in imports

    def test_find_methods(self):
        """测试查找方法"""
        code = """
class MyStrategy:
    def __init__(self):
        pass

    def on_bar(self):
        pass

    def on_stop(self):
        pass
"""
        tree = self.parser.parse(code)
        methods = self.parser.find_methods(tree)

        assert "__init__" in methods
        assert "on_bar" in methods
        assert "on_stop" in methods

    def test_has_external_trading_import(self):
        """测试是否含有第三方交易框架导入"""
        code_with_external = """
from external_trader.trading.strategy import Strategy
"""
        code_without_external = """
from strategy.core import StrategyBase
"""

        tree1 = self.parser.parse(code_with_external)
        tree2 = self.parser.parse(code_without_external)

        assert self.parser._has_external_trading_import(tree1) is True
        assert self.parser._has_external_trading_import(tree2) is False

    def test_extract_params_from_config_class(self):
        """测试从配置类提取参数"""
        code = """
class MyConfig(StrategyConfig):
    def __init__(self, instrument_ids, bar_types, param1=10, param2="test"):
        pass
"""
        tree = self.parser.parse(code)
        config_classes = self.parser.find_config_classes(tree)

        params = self.parser.extract_params_from_config_class(config_classes[0].class_node, code)

        # 应该跳过instrument_ids和bar_types
        param_names = [p["name"] for p in params]
        assert "instrument_ids" not in param_names
        assert "bar_types" not in param_names
        assert "param1" in param_names
        assert "param2" in param_names

    def test_extract_params_from_strategy_class(self):
        """测试从策略类提取参数（Legacy格式）"""
        code = """
class MyStrategy(StrategyBase):
    param1 = 10  # 参数1
    param2 = "test"  # 参数2
    _private = "ignored"
"""
        tree = self.parser.parse(code)
        strategy_classes = self.parser.find_strategy_classes(tree)

        params = self.parser.extract_params_from_strategy_class(strategy_classes[0].class_node, code)

        param_names = [p["name"] for p in params]
        assert "param1" in param_names
        assert "param2" in param_names
        assert "_private" not in param_names

        # 检查描述提取
        for p in params:
            if p["name"] == "param1":
                assert p["description"] == "参数1"
            elif p["name"] == "param2":
                assert p["description"] == "参数2"


class TestParseStrategyCode:
    """parse_strategy_code 函数测试"""

    def test_parse_valid_strategy(self):
        """测试解析有效策略"""
        code = """
class MyStrategy(StrategyBase):
    def __init__(self):
        self.param = 10

    def on_bar(self):
        pass
"""
        result = parse_strategy_code(code)

        assert result["success"] is True
        assert len(result["strategy_classes"]) == 1
        assert result["strategy_classes"][0]["class_name"] == "MyStrategy"

    def test_parse_invalid_code(self):
        """测试解析无效代码"""
        code = "def foo(:"
        result = parse_strategy_code(code)

        assert result["success"] is False
        assert "error" in result


class TestStrategyClassInfo:
    """StrategyClassInfo 数据类测试"""

    def test_to_dict(self):
        """测试转换为字典"""
        import ast

        code = "class MyStrategy(StrategyBase): pass"
        tree = ast.parse(code)
        class_node = tree.body[0]

        info = StrategyClassInfo(
            class_node=class_node,
            class_name="MyStrategy",
            base_classes=["StrategyBase"],
            is_strategy_class=True,
            is_config_class=False,
        )

        result = info.to_dict()

        assert result["class_name"] == "MyStrategy"
        assert result["base_classes"] == ["StrategyBase"]
        assert result["is_strategy_class"] is True
        assert result["is_config_class"] is False
        assert "line_number" in result
        assert "col_offset" in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
