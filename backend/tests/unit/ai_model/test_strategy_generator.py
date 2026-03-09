"""StrategyGenerator 单元测试

测试策略生成器的初始化、代码提取、响应解析和错误处理功能
"""

import importlib.util
import sys
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

# 直接从文件加载模块，避免触发 ai_model/__init__.py 的完整导入链
# 使用绝对路径
_test_file = Path(__file__).resolve()
_backend_dir = _test_file.parent.parent.parent.parent  # tests/unit/ai_model -> tests/unit -> tests -> backend
_ai_model_dir = _backend_dir / "ai_model"
_prompts_dir = _ai_model_dir / "prompts"

# 加载 prompts.manager 模块
spec = importlib.util.spec_from_file_location(
    "prompts.manager", _prompts_dir / "manager.py"
)
assert spec is not None and spec.loader is not None, "无法加载 prompts.manager 模块"
manager_module = importlib.util.module_from_spec(spec)
sys.modules["prompts.manager"] = manager_module
spec.loader.exec_module(manager_module)

PromptCategory = manager_module.PromptCategory
PromptManager = manager_module.PromptManager

# 创建 prompts 包模块
prompts_module = type(sys)('prompts')
prompts_module.PromptCategory = PromptCategory
prompts_module.PromptManager = PromptManager
sys.modules["prompts"] = prompts_module

# 设置 ai_model 包
ai_model_module = type(sys)('ai_model')
ai_model_module.prompts = prompts_module
sys.modules["ai_model"] = ai_model_module
sys.modules["ai_model.prompts"] = prompts_module

# 加载 performance_monitor 模块
spec_pm = importlib.util.spec_from_file_location(
    "performance_monitor", _ai_model_dir / "performance_monitor.py"
)
assert spec_pm is not None and spec_pm.loader is not None, "无法加载 performance_monitor 模块"
pm_module = importlib.util.module_from_spec(spec_pm)
sys.modules["performance_monitor"] = pm_module
spec_pm.loader.exec_module(pm_module)

# 将 performance_monitor 添加到 ai_model 包
ai_model_module.performance_monitor = pm_module
sys.modules["ai_model.performance_monitor"] = pm_module

# 模拟 thinking_chain 模块
thinking_chain_module = type(sys)('thinking_chain')


# 创建模拟的 ThinkingChainManager 类
class MockThinkingChainManager:
    @staticmethod
    def get_active_chain_by_type(chain_type):
        # 返回默认的思维链配置
        return {
            "id": "mock-chain-id",
            "chain_type": chain_type,
            "name": "默认思维链",
            "description": "默认思维链配置",
            "steps": [
                {"key": "analyze_requirement", "title": "分析需求", "description": "分析用户策略需求"},
                {"key": "design_strategy", "title": "设计策略", "description": "设计交易策略逻辑"},
                {"key": "generate_code", "title": "生成代码", "description": "生成策略代码"},
                {"key": "optimize", "title": "优化完善", "description": "优化代码结构"},
            ],
            "is_active": True,
        }


thinking_chain_module.ThinkingChainManager = MockThinkingChainManager
sys.modules["thinking_chain"] = thinking_chain_module
sys.modules["ai_model.thinking_chain"] = thinking_chain_module
ai_model_module.thinking_chain = thinking_chain_module

# 加载 strategy_generator 模块
spec_sg = importlib.util.spec_from_file_location(
    "strategy_generator", _ai_model_dir / "strategy_generator.py"
)
assert spec_sg is not None and spec_sg.loader is not None, "无法加载 strategy_generator 模块"
sg_module = importlib.util.module_from_spec(spec_sg)

# 注册 strategy_generator 模块
sys.modules["strategy_generator"] = sg_module

# 执行模块
spec_sg.loader.exec_module(sg_module)

# 将 strategy_generator 添加到 ai_model 包
ai_model_module.strategy_generator = sg_module
sys.modules["ai_model.strategy_generator"] = sg_module

# 导出需要的类和函数
StrategyGenerator = sg_module.StrategyGenerator
StrategyGenerationError = sg_module.StrategyGenerationError
APIAuthenticationError = sg_module.APIAuthenticationError
APIConnectionError = sg_module.APIConnectionError
APIRateLimitError = sg_module.APIRateLimitError
ResponseParseError = sg_module.ResponseParseError


class TestStrategyGeneratorInit:
    """测试 StrategyGenerator 初始化"""

    def test_init_with_required_params(self):
        """测试使用必需参数初始化"""
        with patch("strategy_generator.OpenAI") as mock_openai:
            mock_client = MagicMock()
            mock_openai.return_value = mock_client

            generator = StrategyGenerator(api_key="test-key")

            assert generator.api_key == "test-key"
            assert generator.api_host == StrategyGenerator.DEFAULT_API_HOST
            assert generator.model_id == StrategyGenerator.DEFAULT_MODEL
            assert generator.temperature == StrategyGenerator.DEFAULT_TEMPERATURE

    def test_init_with_all_params(self):
        """测试使用所有参数初始化"""
        with patch("strategy_generator.OpenAI") as mock_openai:
            mock_client = MagicMock()
            mock_openai.return_value = mock_client

            generator = StrategyGenerator(
                api_key="test-key",
                api_host="https://custom.api.com",
                model_id="gpt-4-turbo",
                temperature=0.5,
            )

            assert generator.api_key == "test-key"
            assert generator.api_host == "https://custom.api.com"
            assert generator.model_id == "gpt-4-turbo"
            assert generator.temperature == 0.5

    def test_init_api_host_trailing_slash(self):
        """测试 API host 去除尾部斜杠"""
        with patch("strategy_generator.OpenAI") as mock_openai:
            mock_client = MagicMock()
            mock_openai.return_value = mock_client

            generator = StrategyGenerator(
                api_key="test-key",
                api_host="https://api.example.com/",
            )

            # 内部会去除尾部斜杠并添加 /v1
            assert generator.api_host == "https://api.example.com"

    def test_init_creates_openai_client(self):
        """测试初始化创建 OpenAI 客户端"""
        with patch("strategy_generator.OpenAI") as mock_openai:
            mock_client = MagicMock()
            mock_openai.return_value = mock_client

            StrategyGenerator(api_key="test-key")

            mock_openai.assert_called_once()
            call_kwargs = mock_openai.call_args.kwargs
            assert call_kwargs["api_key"] == "test-key"
            assert call_kwargs["base_url"] == "https://api.openai.com/v1"

    def test_get_base_url_adds_v1(self):
        """测试 _get_base_url 方法添加 /v1"""
        with patch("strategy_generator.OpenAI") as mock_openai:
            mock_client = MagicMock()
            mock_openai.return_value = mock_client

            generator = StrategyGenerator(
                api_key="test-key",
                api_host="https://api.example.com",
            )

            base_url = generator._get_base_url()
            assert base_url == "https://api.example.com/v1"

    def test_get_base_url_no_duplicate_v1(self):
        """测试 _get_base_url 不重复添加 /v1"""
        with patch("strategy_generator.OpenAI") as mock_openai:
            mock_client = MagicMock()
            mock_openai.return_value = mock_client

            generator = StrategyGenerator(
                api_key="test-key",
                api_host="https://api.example.com/v1",
            )

            base_url = generator._get_base_url()
            assert base_url == "https://api.example.com/v1"


class TestStrategyGeneratorCodeExtraction:
    """测试 StrategyGenerator 代码提取功能"""

    @pytest.fixture
    def generator(self):
        """创建测试用的生成器实例"""
        with patch("strategy_generator.OpenAI") as mock_openai:
            mock_client = MagicMock()
            mock_openai.return_value = mock_client
            return StrategyGenerator(api_key="test-key")

    def test_extract_code_with_python_markers(self, generator):
        """测试提取带 python 标记的代码块"""
        content = '''Some text
```python
class MyStrategy:
    pass
```
More text'''

        code = generator._extract_code(content)
        assert "class MyStrategy:" in code
        assert "```" not in code

    def test_extract_code_with_generic_markers(self, generator):
        """测试提取通用代码块"""
        content = '''Some text
```
def hello():
    pass
```
More text'''

        code = generator._extract_code(content)
        assert "def hello():" in code
        assert "```" not in code

    def test_extract_code_single_line(self, generator):
        """测试提取单行代码块"""
        content = '```python\nclass Test: pass\n```'

        code = generator._extract_code(content)
        assert "class Test: pass" in code

    def test_extract_code_python_indicators(self, generator):
        """测试通过 Python 关键字识别代码"""
        content = '''class MyStrategy:
    def __init__(self):
        pass'''

        code = generator._extract_code(content)
        assert "class MyStrategy:" in code

    def test_extract_code_import_indicator(self, generator):
        """测试通过 import 关键字识别代码"""
        content = '''import numpy as np
from typing import List'''

        code = generator._extract_code(content)
        assert "import numpy" in code

    def test_extract_code_def_indicator(self, generator):
        """测试通过 def 关键字识别代码"""
        content = '''def calculate():
    return 42'''

        code = generator._extract_code(content)
        assert "def calculate():" in code

    def test_extract_code_comment_indicator(self, generator):
        """测试通过注释识别代码"""
        content = '''# This is a comment
class Strategy:
    pass'''

        code = generator._extract_code(content)
        assert "# This is a comment" in code

    def test_extract_code_docstring_indicator(self, generator):
        """测试通过文档字符串识别代码"""
        content = '''"""Strategy module"""
class MyStrategy:
    pass'''

        code = generator._extract_code(content)
        assert '"""Strategy module"""' in code

    def test_extract_code_empty_content(self, generator):
        """测试空内容返回 None"""
        code = generator._extract_code("")
        assert code is None

    def test_extract_code_whitespace_only(self, generator):
        """测试仅空白内容返回 None"""
        code = generator._extract_code("   \n\t  ")
        assert code is None

    def test_extract_code_no_markers_no_indicators(self, generator):
        """测试无标记无指示符时返回原内容"""
        content = "Plain text without code"
        code = generator._extract_code(content)
        assert code == content.strip()

    def test_extract_code_multiple_code_blocks(self, generator):
        """测试多个代码块时提取第一个"""
        content = '''```python
first block
```
```python
second block
```'''

        code = generator._extract_code(content)
        assert "first block" in code
        assert "second block" not in code


class TestStrategyGeneratorResponseParsing:
    """测试 StrategyGenerator 响应解析功能"""

    @pytest.fixture
    def generator(self):
        """创建测试用的生成器实例"""
        with patch("strategy_generator.OpenAI") as mock_openai:
            mock_client = MagicMock()
            mock_openai.return_value = mock_client
            return StrategyGenerator(api_key="test-key")

    def test_parse_response_success(self, generator):
        """测试成功解析响应"""
        content = '''```python
class MyStrategy:
    def __init__(self):
        pass
```'''

        result = generator._parse_response(content)

        assert result["success"] is True
        assert "class MyStrategy:" in result["code"]
        assert result["raw_content"] == content
        assert result["error"] is None

    def test_parse_response_empty_content(self, generator):
        """测试空内容解析失败"""
        result = generator._parse_response("")

        assert result["success"] is False
        assert result["code"] is None
        assert "为空" in result["error"]

    def test_parse_response_whitespace_content(self, generator):
        """测试空白内容解析失败"""
        result = generator._parse_response("   \n  ")

        assert result["success"] is False
        assert result["code"] is None
        assert "为空" in result["error"]

    def test_parse_response_no_code_extracted(self, generator):
        """测试无法提取代码时返回原内容作为代码"""
        content = "Just plain text without any code blocks"

        result = generator._parse_response(content)

        # 纯文本内容会被当作代码返回
        assert result["success"] is True
        assert result["code"] == content

    def test_parse_response_preserves_raw_content(self, generator):
        """测试解析保留原始内容"""
        content = "Original response content"

        result = generator._parse_response(content)

        assert result["raw_content"] == content


class TestStrategyGeneratorErrorHandling:
    """测试 StrategyGenerator 错误处理"""

    @pytest.fixture
    def generator(self):
        """创建测试用的生成器实例"""
        with patch("strategy_generator.OpenAI") as mock_openai:
            mock_client = MagicMock()
            mock_openai.return_value = mock_client
            return StrategyGenerator(api_key="test-key")

    @pytest.mark.asyncio
    async def test_generate_strategy_stream_authentication_error(self, generator):
        """测试流式生成时认证错误处理"""
        from openai import AuthenticationError

        with patch.object(generator._client.chat.completions, "create") as mock_create:
            mock_create.side_effect = AuthenticationError(
                "Invalid API key",
                response=MagicMock(),
                body=None
            )

            chunks = []
            async for chunk in generator.generate_strategy_stream("test requirement"):
                chunks.append(chunk)

            # 现在会返回思维链事件 + 错误事件
            assert len(chunks) >= 2
            # 最后一个chunk应该是错误
            assert chunks[-1]["type"] == "error"
            assert "api_authentication_error" == chunks[-1]["error_code"]
            assert "API密钥无效" in chunks[-1]["error"]
            # 检查思维链事件
            thinking_chain_chunks = [c for c in chunks if c["type"] == "thinking_chain"]
            assert len(thinking_chain_chunks) >= 1

    @pytest.mark.asyncio
    async def test_generate_strategy_stream_rate_limit_error(self, generator):
        """测试流式生成时速率限制错误处理"""
        from openai import RateLimitError

        with patch.object(generator._client.chat.completions, "create") as mock_create:
            mock_create.side_effect = RateLimitError(
                "Rate limit exceeded",
                response=MagicMock(),
                body=None
            )

            chunks = []
            async for chunk in generator.generate_strategy_stream("test requirement"):
                chunks.append(chunk)

            # 现在会返回思维链事件 + 错误事件
            assert len(chunks) >= 2
            # 最后一个chunk应该是错误
            assert chunks[-1]["type"] == "error"
            assert "api_rate_limit_error" == chunks[-1]["error_code"]
            assert "请求过于频繁" in chunks[-1]["error"]

    @pytest.mark.asyncio
    async def test_generate_strategy_stream_timeout_error(self, generator):
        """测试流式生成时超时错误处理"""
        from openai import APITimeoutError

        with patch.object(generator._client.chat.completions, "create") as mock_create:
            mock_create.side_effect = APITimeoutError("Request timed out")

            chunks = []
            async for chunk in generator.generate_strategy_stream("test requirement"):
                chunks.append(chunk)

            # 现在会返回思维链事件 + 错误事件
            assert len(chunks) >= 2
            # 最后一个chunk应该是错误
            assert chunks[-1]["type"] == "error"
            assert "api_connection_error" == chunks[-1]["error_code"]
            assert "超时" in chunks[-1]["error"]

    @pytest.mark.asyncio
    async def test_generate_strategy_stream_connection_error(self, generator):
        """测试流式生成时连接错误处理"""
        # 模拟连接错误
        with patch.object(generator._client.chat.completions, "create") as mock_create:
            mock_create.side_effect = Exception("Connection failed")

            chunks = []
            async for chunk in generator.generate_strategy_stream("test requirement"):
                chunks.append(chunk)

            # 现在会返回思维链事件 + 错误事件
            assert len(chunks) >= 2
            # 最后一个chunk应该是错误
            assert chunks[-1]["type"] == "error"

    @pytest.mark.asyncio
    async def test_generate_strategy_stream_generic_exception(self, generator):
        """测试流式生成时通用异常处理"""
        with patch.object(generator._client.chat.completions, "create") as mock_create:
            mock_create.side_effect = Exception("Unexpected error")

            chunks = []
            async for chunk in generator.generate_strategy_stream("test requirement"):
                chunks.append(chunk)

            # 现在会返回思维链事件 + 错误事件
            assert len(chunks) >= 2
            # 最后一个chunk应该是错误
            assert chunks[-1]["type"] == "error"
            assert "generation_failed" == chunks[-1]["error_code"]
            assert "策略生成失败" in chunks[-1]["error"]

    def test_generate_strategy_authentication_error(self, generator):
        """测试同步生成时认证错误处理"""
        from openai import AuthenticationError

        with patch.object(generator._client.chat.completions, "create") as mock_create:
            mock_create.side_effect = AuthenticationError(
                "Invalid API key",
                response=MagicMock(),
                body=None
            )

            with pytest.raises(APIAuthenticationError) as exc_info:
                generator.generate_strategy("test requirement")

            assert exc_info.value.error_code == "api_authentication_error"
            assert "API密钥无效" in exc_info.value.message

    def test_generate_strategy_rate_limit_error(self, generator):
        """测试同步生成时速率限制错误处理"""
        from openai import RateLimitError

        with patch.object(generator._client.chat.completions, "create") as mock_create:
            mock_create.side_effect = RateLimitError(
                "Rate limit exceeded",
                response=MagicMock(),
                body=None
            )

            with pytest.raises(APIRateLimitError) as exc_info:
                generator.generate_strategy("test requirement")

            assert exc_info.value.error_code == "api_rate_limit_error"
            assert "请求过于频繁" in exc_info.value.message

    def test_generate_strategy_timeout_error(self, generator):
        """测试同步生成时超时错误处理"""
        from openai import APITimeoutError

        with patch.object(generator._client.chat.completions, "create") as mock_create:
            mock_create.side_effect = APITimeoutError("Request timed out")

            with pytest.raises(APIConnectionError) as exc_info:
                generator.generate_strategy("test requirement")

            assert exc_info.value.error_code == "api_connection_error"
            assert "超时" in exc_info.value.message

    def test_generate_strategy_connection_error(self, generator):
        """测试同步生成时连接错误处理"""
        # 使用通用的 Exception 来模拟连接错误
        with patch.object(generator._client.chat.completions, "create") as mock_create:
            mock_create.side_effect = Exception("Connection failed")

            with pytest.raises(StrategyGenerationError) as exc_info:
                generator.generate_strategy("test requirement")

            assert exc_info.value.error_code == "generation_failed"


class TestStrategyGeneratorValidation:
    """测试 StrategyGenerator 代码验证功能"""

    @pytest.fixture
    def generator(self):
        """创建测试用的生成器实例"""
        with patch("strategy_generator.OpenAI") as mock_openai:
            mock_client = MagicMock()
            mock_openai.return_value = mock_client
            return StrategyGenerator(api_key="test-key")

    def test_validate_code_valid(self, generator):
        """测试验证有效代码"""
        code = '''class MyStrategy:
    def __init__(self):
        pass

    def on_bar(self, data):
        return data'''

        result = generator.validate_code(code)

        assert result["valid"] is True
        assert len([e for e in result["errors"] if not e.startswith("警告")]) == 0

    def test_validate_code_empty(self, generator):
        """测试验证空代码"""
        result = generator.validate_code("")

        assert result["valid"] is False
        assert any("为空" in e for e in result["errors"])

    def test_validate_code_syntax_error(self, generator):
        """测试验证语法错误代码"""
        code = '''class MyStrategy
    def __init__(self):
        pass'''

        result = generator.validate_code(code)

        assert result["valid"] is False
        assert any("语法错误" in e for e in result["errors"])

    def test_validate_code_missing_class_warning(self, generator):
        """测试验证缺少类定义的警告"""
        code = '''def standalone_function():
    return 42'''

        result = generator.validate_code(code)

        # 语法正确但缺少类定义
        assert any("未找到类定义" in e for e in result["errors"])

    def test_validate_code_missing_function_warning(self, generator):
        """测试验证缺少函数定义的警告"""
        code = '''x = 42'''

        result = generator.validate_code(code)

        assert any("未找到函数定义" in e for e in result["errors"])


class TestStrategyGeneratorBuildPrompt:
    """测试 StrategyGenerator 提示词构建功能"""

    @pytest.fixture
    def generator(self):
        """创建测试用的生成器实例"""
        with patch("strategy_generator.OpenAI") as mock_openai:
            mock_client = MagicMock()
            mock_openai.return_value = mock_client
            return StrategyGenerator(api_key="test-key")

    def test_build_prompt_with_default_vars(self, generator):
        """测试使用默认变量构建提示词"""
        with patch.object(generator._prompt_manager, "render") as mock_render:
            mock_render.return_value = "rendered prompt"

            result = generator._build_prompt(
                "my requirement",
                PromptCategory.STRATEGY_GENERATION
            )

            assert result == "rendered prompt"
            mock_render.assert_called_once()
            call_kwargs = mock_render.call_args.kwargs
            assert call_kwargs["user_description"] == "my requirement"
            assert call_kwargs["strategy_name"] == "GeneratedStrategy"
            assert call_kwargs["symbol"] == "BTC/USDT"

    def test_build_prompt_with_custom_vars(self, generator):
        """测试使用自定义变量构建提示词"""
        with patch.object(generator._prompt_manager, "render") as mock_render:
            mock_render.return_value = "rendered prompt"

            result = generator._build_prompt(
                "my requirement",
                PromptCategory.STRATEGY_GENERATION,
                strategy_name="CustomStrategy",
                symbol="ETH/USDT",
                timeframe="4h"
            )

            call_kwargs = mock_render.call_args.kwargs
            assert call_kwargs["strategy_name"] == "CustomStrategy"
            assert call_kwargs["symbol"] == "ETH/USDT"
            assert call_kwargs["timeframe"] == "4h"


class TestStrategyGeneratorConstants:
    """测试 StrategyGenerator 常量"""

    def test_default_constants(self):
        """测试默认常量值"""
        assert StrategyGenerator.DEFAULT_API_HOST == "https://api.openai.com"
        assert StrategyGenerator.DEFAULT_MODEL == "gpt-4"
        assert StrategyGenerator.DEFAULT_TEMPERATURE == 0.7
        assert StrategyGenerator.DEFAULT_MAX_TOKENS == 4096


class TestStrategyGenerationErrorClasses:
    """测试策略生成错误类"""

    def test_base_error(self):
        """测试基础错误类"""
        error = StrategyGenerationError("Test message", "test_code")
        assert error.message == "Test message"
        assert error.error_code == "test_code"
        assert str(error) == "Test message"

    def test_authentication_error(self):
        """测试认证错误类"""
        error = APIAuthenticationError("Auth failed")
        assert error.message == "Auth failed"
        assert error.error_code == "api_authentication_error"

    def test_connection_error(self):
        """测试连接错误类"""
        error = APIConnectionError("Connection failed")
        assert error.message == "Connection failed"
        assert error.error_code == "api_connection_error"

    def test_rate_limit_error(self):
        """测试速率限制错误类"""
        error = APIRateLimitError("Rate limited")
        assert error.message == "Rate limited"
        assert error.error_code == "api_rate_limit_error"

    def test_parse_error(self):
        """测试解析错误类"""
        error = ResponseParseError("Parse failed")
        assert error.message == "Parse failed"
        assert error.error_code == "response_parse_error"
