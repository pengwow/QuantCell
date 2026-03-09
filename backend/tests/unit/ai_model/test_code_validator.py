"""CodeValidator 单元测试

测试代码验证器的语法验证、结构验证、风格验证功能
"""

import importlib.util
import sys
from pathlib import Path

import pytest

# 直接从文件加载模块，避免触发 ai_model/__init__.py 的完整导入链
# 使用绝对路径
_test_file = Path(__file__).resolve()
_backend_dir = _test_file.parent.parent.parent.parent  # tests/unit/ai_model -> tests/unit -> tests -> backend
_ai_model_dir = _backend_dir / "ai_model"

# 加载 code_validator 模块
spec = importlib.util.spec_from_file_location(
    "code_validator", _ai_model_dir / "code_validator.py"
)
assert spec is not None and spec.loader is not None, "无法加载 code_validator 模块"
cv_module = importlib.util.module_from_spec(spec)
sys.modules["code_validator"] = cv_module
spec.loader.exec_module(cv_module)

CodeValidator = cv_module.CodeValidator
ValidationError = cv_module.ValidationError
ValidationWarning = cv_module.ValidationWarning


class TestValidationError:
    """测试 ValidationError 数据类"""

    def test_to_dict(self):
        """测试错误信息转换为字典"""
        error = ValidationError(
            type="syntax_error",
            line=10,
            column=5,
            message="语法错误: 无效语法",
        )
        result = error.to_dict()

        assert result["type"] == "syntax_error"
        assert result["line"] == 10
        assert result["column"] == 5
        assert result["message"] == "语法错误: 无效语法"


class TestValidationWarning:
    """测试 ValidationWarning 数据类"""

    def test_to_dict(self):
        """测试警告信息转换为字典"""
        warning = ValidationWarning(
            type="style_warning",
            line=20,
            column=0,
            message="行长度超过限制",
        )
        result = warning.to_dict()

        assert result["type"] == "style_warning"
        assert result["line"] == 20
        assert result["column"] == 0
        assert result["message"] == "行长度超过限制"


class TestCodeValidatorInit:
    """测试 CodeValidator 初始化"""

    def test_init_with_defaults(self):
        """测试使用默认参数初始化"""
        validator = CodeValidator()

        assert validator.max_line_length == CodeValidator.DEFAULT_MAX_LINE_LENGTH
        assert validator.required_class_name == CodeValidator.DEFAULT_REQUIRED_CLASS_NAME
        assert validator.required_methods == CodeValidator.DEFAULT_REQUIRED_METHODS

    def test_init_with_custom_params(self):
        """测试使用自定义参数初始化"""
        validator = CodeValidator(
            max_line_length=80,
            required_class_name="MyStrategy",
            required_methods=["on_bar", "on_start", "on_stop"],
        )

        assert validator.max_line_length == 80
        assert validator.required_class_name == "MyStrategy"
        assert validator.required_methods == ["on_bar", "on_start", "on_stop"]

    def test_init_required_methods_copy(self):
        """测试必需方法列表被正确复制"""
        methods = ["method1", "method2"]
        validator1 = CodeValidator(required_methods=methods)
        validator2 = CodeValidator(required_methods=methods)

        # 修改validator1的方法列表不应影响validator2
        validator1.required_methods.append("method3")
        assert "method3" not in validator2.required_methods


class TestValidateSyntax:
    """测试语法验证功能"""

    @pytest.fixture
    def validator(self):
        """创建测试用的验证器实例"""
        return CodeValidator()

    def test_valid_syntax(self, validator):
        """测试语法正确的代码"""
        code = '''class MyStrategy:
    def on_bar(self, data):
        return data
'''
        errors, warnings = validator.validate_syntax(code)

        assert len(errors) == 0
        assert len(warnings) == 0

    def test_empty_code(self, validator):
        """测试空代码"""
        errors, warnings = validator.validate_syntax("")

        assert len(errors) == 1
        assert errors[0].type == "syntax_error"
        assert errors[0].line == 0
        assert "为空" in errors[0].message

    def test_whitespace_only_code(self, validator):
        """测试仅包含空白字符的代码"""
        errors, warnings = validator.validate_syntax("   \n\t  ")

        assert len(errors) == 1
        assert errors[0].type == "syntax_error"
        assert "为空" in errors[0].message

    def test_syntax_error_missing_colon(self, validator):
        """测试语法错误：缺少冒号"""
        code = '''class MyStrategy
    def on_bar(self):
        pass
'''
        errors, warnings = validator.validate_syntax(code)

        assert len(errors) == 1
        assert errors[0].type == "syntax_error"
        assert "语法错误" in errors[0].message
        assert errors[0].line == 1

    def test_syntax_error_unmatched_parenthesis(self, validator):
        """测试语法错误：括号不匹配"""
        code = '''class MyStrategy:
    def on_bar(self, data:
        pass
'''
        errors, warnings = validator.validate_syntax(code)

        assert len(errors) == 1
        assert errors[0].type == "syntax_error"
        assert "语法错误" in errors[0].message

    def test_indentation_error(self, validator):
        """测试缩进错误"""
        code = '''class MyStrategy:
def on_bar(self):
    pass
'''
        errors, warnings = validator.validate_syntax(code)

        assert len(errors) == 1
        assert errors[0].type == "indentation_error"
        assert "缩进错误" in errors[0].message

    def test_indentation_error_inconsistent(self, validator):
        """测试不一致的缩进"""
        code = '''class MyStrategy:
    def on_bar(self):
       pass
      return
'''
        errors, warnings = validator.validate_syntax(code)

        assert len(errors) == 1
        assert errors[0].type == "indentation_error"


class TestValidateStructure:
    """测试结构验证功能"""

    @pytest.fixture
    def validator(self):
        """创建测试用的验证器实例"""
        return CodeValidator()

    def test_valid_structure(self, validator):
        """测试结构正确的代码"""
        code = '''class MyStrategy:
    def __init__(self):
        pass

    def on_bar(self, bar):
        pass
'''
        errors, warnings = validator.validate_structure(code)

        # 应该没有错误（包含Strategy类名和on_bar方法）
        structure_errors = [e for e in errors if e.type == "structure_error"]
        assert len(structure_errors) == 0

    def test_missing_class(self, validator):
        """测试缺少类定义"""
        code = '''def on_bar(bar):
    pass
'''
        errors, warnings = validator.validate_structure(code)

        assert len(errors) == 1
        assert errors[0].type == "structure_error"
        assert "未找到类定义" in errors[0].message

    def test_missing_required_method(self, validator):
        """测试缺少必需方法"""
        code = '''class MyStrategy:
    def __init__(self):
        pass

    def other_method(self):
        pass
'''
        errors, warnings = validator.validate_structure(code)

        assert len(errors) == 1
        assert errors[0].type == "structure_error"
        assert "on_bar" in errors[0].message
        assert "缺少必需方法" in errors[0].message

    def test_strategy_in_base_class(self, validator):
        """测试Strategy在基类中"""
        code = '''class MyStrategy(Strategy):
    def on_bar(self, bar):
        pass
'''
        errors, warnings = validator.validate_structure(code)

        structure_errors = [e for e in errors if e.type == "structure_error"]
        assert len(structure_errors) == 0

    def test_strategy_in_module_base_class(self, validator):
        """测试Strategy在模块基类中"""
        code = '''class MyStrategy(core.Strategy):
    def on_bar(self, bar):
        pass
'''
        errors, warnings = validator.validate_structure(code)

        structure_errors = [e for e in errors if e.type == "structure_error"]
        assert len(structure_errors) == 0

    def test_missing_init_warning(self, validator):
        """测试缺少__init__方法的警告"""
        code = '''class MyStrategy:
    def on_bar(self, bar):
        pass
'''
        errors, warnings = validator.validate_structure(code)

        init_warnings = [w for w in warnings if "__init__" in w.message]
        assert len(init_warnings) == 1
        assert init_warnings[0].type == "structure_warning"

    def test_no_strategy_in_class_name_warning(self, validator):
        """测试类名不含Strategy的警告"""
        code = '''class MyClass:
    def on_bar(self, bar):
        pass
'''
        errors, warnings = validator.validate_structure(code)

        strategy_warnings = [w for w in warnings if "Strategy" in w.message]
        assert len(strategy_warnings) == 1
        assert strategy_warnings[0].type == "structure_warning"

    def test_empty_code_structure(self, validator):
        """测试空代码的结构验证"""
        errors, warnings = validator.validate_structure("")

        assert len(errors) == 1
        assert errors[0].type == "structure_error"
        assert "为空" in errors[0].message

    def test_syntax_error_skips_structure_check(self, validator):
        """测试语法错误时跳过后续结构检查"""
        code = '''class MyStrategy
    def on_bar(self):
        pass
'''
        # 语法错误的代码在structure验证中应该返回空（因为无法解析）
        errors, warnings = validator.validate_structure(code)

        # 语法错误已在validate_syntax中处理，这里应该返回空
        assert len(errors) == 0
        assert len(warnings) == 0


class TestValidateStyle:
    """测试风格验证功能"""

    @pytest.fixture
    def validator(self):
        """创建测试用的验证器实例"""
        return CodeValidator(max_line_length=120)

    def test_valid_style(self, validator):
        """测试风格正确的代码"""
        code = '''class MyStrategy:
    def on_bar(self, bar):
        pass
'''
        errors, warnings = validator.validate_style(code)

        assert len(errors) == 0
        # 可能有文件末尾换行符的警告

    def test_line_length_exceeded(self, validator):
        """测试行长度超过限制"""
        long_line = "x" * 130
        code = f'''class MyStrategy:
    def on_bar(self, bar):
        {long_line}
'''
        errors, warnings = validator.validate_style(code)

        length_warnings = [w for w in warnings if "行长度" in w.message]
        assert len(length_warnings) >= 1
        assert length_warnings[0].type == "style_warning"
        assert "超过限制" in length_warnings[0].message

    def test_tab_indentation(self, validator):
        """测试Tab缩进警告"""
        code = "class MyStrategy:\n\tdef on_bar(self):\n\t\tpass\n"
        errors, warnings = validator.validate_style(code)

        tab_warnings = [w for w in warnings if "Tab" in w.message]
        assert len(tab_warnings) >= 1
        assert tab_warnings[0].type == "style_warning"
        assert "Tab缩进" in tab_warnings[0].message

    def test_trailing_whitespace(self, validator):
        """测试行尾空格警告"""
        code = '''class MyStrategy:
    def on_bar(self, bar):   
        pass
'''
        errors, warnings = validator.validate_style(code)

        trailing_warnings = [w for w in warnings if "行尾" in w.message]
        assert len(trailing_warnings) >= 1
        assert trailing_warnings[0].type == "style_warning"

    def test_missing_final_newline(self, validator):
        """测试缺少文件末尾换行符警告"""
        code = '''class MyStrategy:
    def on_bar(self, bar):
        pass'''
        errors, warnings = validator.validate_style(code)

        newline_warnings = [w for w in warnings if "换行符" in w.message]
        assert len(newline_warnings) >= 1
        assert any("缺少" in w.message for w in newline_warnings)

    def test_extra_final_newlines(self, validator):
        """测试文件末尾多余空行警告"""
        code = '''class MyStrategy:
    def on_bar(self, bar):
        pass

'''
        errors, warnings = validator.validate_style(code)

        newline_warnings = [w for w in warnings if "空行" in w.message]
        # 应该检测到多余空行
        assert len(newline_warnings) >= 1

    def test_empty_code_style(self, validator):
        """测试空代码的风格验证"""
        errors, warnings = validator.validate_style("")

        assert len(errors) == 0
        assert len(warnings) == 0

    def test_custom_max_line_length(self):
        """测试自定义最大行长度"""
        validator = CodeValidator(max_line_length=50)
        code = '''class MyStrategy:
    def on_bar(self, bar):
        x = "this is a long line that exceeds fifty characters"
'''
        errors, warnings = validator.validate_style(code)

        length_warnings = [w for w in warnings if "行长度" in w.message]
        assert len(length_warnings) >= 1


class TestValidate:
    """测试综合验证功能"""

    @pytest.fixture
    def validator(self):
        """创建测试用的验证器实例"""
        return CodeValidator()

    def test_valid_code(self, validator):
        """测试完全有效的代码"""
        code = '''class MyStrategy:
    def __init__(self):
        pass

    def on_bar(self, bar):
        pass
'''
        result = validator.validate(code)

        assert result["valid"] is True
        assert result["summary"]["total_errors"] == 0
        assert result["summary"]["syntax_valid"] is True

    def test_invalid_syntax_code(self, validator):
        """测试语法错误的代码"""
        code = '''class MyStrategy
    def on_bar(self):
        pass
'''
        result = validator.validate(code)

        assert result["valid"] is False
        assert result["summary"]["syntax_valid"] is False
        assert result["summary"]["total_errors"] >= 1
        assert any(e["type"] == "syntax_error" for e in result["errors"])

    def test_invalid_structure_code(self, validator):
        """测试结构错误的代码"""
        code = '''class MyStrategy:
    def __init__(self):
        pass
'''
        result = validator.validate(code)

        assert result["valid"] is False
        assert result["summary"]["syntax_valid"] is True
        assert any(e["type"] == "structure_error" for e in result["errors"])

    def test_code_with_warnings_only(self, validator):
        """测试只有警告没有错误的代码"""
        code = '''class MyStrategy:
    def on_bar(self, bar):
        x = "this is a very long line that exceeds the default maximum line length of one hundred and twenty characters"
        pass
'''
        result = validator.validate(code)

        # 可能有警告但没有错误
        assert result["summary"]["syntax_valid"] is True
        assert result["summary"]["total_warnings"] >= 1

    def test_error_format(self, validator):
        """测试错误信息格式"""
        code = '''class MyStrategy
    def on_bar(self):
        pass
'''
        result = validator.validate(code)

        for error in result["errors"]:
            assert "type" in error
            assert "line" in error
            assert "column" in error
            assert "message" in error
            assert isinstance(error["type"], str)
            assert isinstance(error["line"], int)
            assert isinstance(error["column"], int)
            assert isinstance(error["message"], str)

    def test_warning_format(self, validator):
        """测试警告信息格式"""
        code = '''class MyStrategy:
    def on_bar(self, bar):
        pass
'''
        result = validator.validate(code)

        for warning in result["warnings"]:
            assert "type" in warning
            assert "line" in warning
            assert "column" in warning
            assert "message" in warning
            assert isinstance(warning["type"], str)
            assert isinstance(warning["line"], int)
            assert isinstance(warning["column"], int)
            assert isinstance(warning["message"], str)

    def test_empty_code_validation(self, validator):
        """测试空代码的综合验证"""
        result = validator.validate("")

        assert result["valid"] is False
        assert result["summary"]["total_errors"] >= 1
        assert result["summary"]["syntax_valid"] is False


class TestValidateStrategyCode:
    """测试策略代码专门验证功能"""

    @pytest.fixture
    def validator(self):
        """创建测试用的验证器实例"""
        return CodeValidator()

    def test_valid_strategy_code(self, validator):
        """测试有效的策略代码"""
        code = '''from strategy.core import Strategy

class MyStrategy(Strategy):
    def __init__(self):
        pass

    def on_bar(self, bar):
        pass
'''
        result = validator.validate_strategy_code(code)

        assert result["summary"]["syntax_valid"] is True
        # 不应该有策略框架导入警告
        strategy_warnings = [w for w in result["warnings"] if "strategy_warning" == w.get("type")]
        assert len(strategy_warnings) == 0

    def test_strategy_code_without_import(self, validator):
        """测试缺少策略框架导入的代码"""
        code = '''class MyStrategy:
    def on_bar(self, bar):
        pass
'''
        result = validator.validate_strategy_code(code)

        strategy_warnings = [w for w in result["warnings"] if w.get("type") == "strategy_warning"]
        assert len(strategy_warnings) == 1
        assert "策略框架导入" in strategy_warnings[0]["message"]

    def test_strategy_code_with_nautilus_import(self, validator):
        """测试使用nautilus_trader导入的代码"""
        code = '''from nautilus_trader.trading.strategy import Strategy

class MyStrategy(Strategy):
    def on_bar(self, bar):
        pass
'''
        result = validator.validate_strategy_code(code)

        strategy_warnings = [w for w in result["warnings"] if w.get("type") == "strategy_warning"]
        assert len(strategy_warnings) == 0

    def test_strategy_code_syntax_error(self, validator):
        """测试语法错误的策略代码"""
        code = '''class MyStrategy
    def on_bar(self):
        pass
'''
        result = validator.validate_strategy_code(code)

        assert result["summary"]["syntax_valid"] is False
        # 语法错误时不进行策略特定检查


class TestCodeValidatorConstants:
    """测试 CodeValidator 常量"""

    def test_default_constants(self):
        """测试默认常量值"""
        assert CodeValidator.DEFAULT_MAX_LINE_LENGTH == 120
        assert CodeValidator.DEFAULT_REQUIRED_CLASS_NAME == "Strategy"
        assert CodeValidator.DEFAULT_REQUIRED_METHODS == ["on_bar"]


class TestComplexCodeValidation:
    """测试复杂代码验证场景"""

    @pytest.fixture
    def validator(self):
        """创建测试用的验证器实例"""
        return CodeValidator()

    def test_multiple_classes(self, validator):
        """测试多个类的代码"""
        code = '''class Config:
    pass

class MyStrategy:
    def on_bar(self, bar):
        pass
'''
        result = validator.validate(code)

        assert result["summary"]["syntax_valid"] is True
        # 应该识别到包含Strategy的类
        assert result["valid"] is True

    def test_inheritance_chain(self, validator):
        """测试继承链"""
        code = '''class BaseStrategy:
    pass

class MyStrategy(BaseStrategy):
    def on_bar(self, bar):
        pass
'''
        result = validator.validate(code)

        # 类名包含Strategy，应该通过结构检查
        assert result["summary"]["syntax_valid"] is True

    def test_multiple_methods(self, validator):
        """测试多个方法的类"""
        code = '''class MyStrategy:
    def __init__(self):
        pass

    def on_start(self):
        pass

    def on_bar(self, bar):
        pass

    def on_stop(self):
        pass
'''
        result = validator.validate(code)

        assert result["valid"] is True
        assert result["summary"]["syntax_valid"] is True

    def test_decorated_methods(self, validator):
        """测试带装饰器的方法"""
        code = '''class MyStrategy:
    @property
    def name(self):
        return "MyStrategy"

    def on_bar(self, bar):
        pass
'''
        result = validator.validate(code)

        assert result["valid"] is True
        assert result["summary"]["syntax_valid"] is True
