"""StrategyGenerator 单元测试

测试策略生成器的初始化、代码提取、响应解析和错误处理功能
"""

import importlib.util
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# 注入记录表：_inject 会把每个被替换/新增的 sys.modules 条目记录下来，
# teardown_module（pytest 模块级收尾钩子）在全部测试结束后恢复原状，
# 避免顶层包 ai_model/prompts 被假模块永久替换而毒害全仓后续测试。
_SAVED_MODULES: dict[str, object | None] = {}


def _inject(name: str, module: object) -> None:
    """记录并注入模块到 sys.modules（模块级隔离专用）。"""
    _SAVED_MODULES[name] = sys.modules.get(name)
    sys.modules[name] = module


def teardown_module() -> None:
    """恢复本模块注入的所有 sys.modules 条目。"""
    for name, orig in _SAVED_MODULES.items():
        if orig is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = orig
    _SAVED_MODULES.clear()


# 直接从文件加载模块，避免触发 ai/strategy/__init__.py 的完整导入链
# 使用绝对路径
_test_file = Path(__file__).resolve()
_backend_dir = (
    _test_file.parent.parent.parent.parent.parent
)  # tests/unit/ai/strategy -> tests/unit/ai -> tests/unit -> tests -> backend
_strategy_dir = _backend_dir / "ai" / "strategy"
_prompts_dir = _strategy_dir / "prompts"

# 设置 ai 和 ai.strategy 父包（使相对 import .xxx 能解析到 sys.modules）
ai_pkg = type(sys)("ai")
ai_strategy_pkg = type(sys)("ai.strategy")
ai_pkg.strategy = ai_strategy_pkg
_inject("ai", ai_pkg)
_inject("ai.strategy", ai_strategy_pkg)

# 加载 prompts.manager 模块
spec = importlib.util.spec_from_file_location("ai.strategy.prompts.manager", _prompts_dir / "manager.py")
assert spec is not None and spec.loader is not None, "无法加载 prompts.manager 模块"
manager_module = importlib.util.module_from_spec(spec)
_inject("ai.strategy.prompts.manager", manager_module)
spec.loader.exec_module(manager_module)

PromptCategory = manager_module.PromptCategory
PromptManager = manager_module.PromptManager

# 创建 prompts 包模块
prompts_module = type(sys)("ai.strategy.prompts")
prompts_module.PromptCategory = PromptCategory
prompts_module.PromptManager = PromptManager
prompts_module.manager = manager_module
_inject("ai.strategy.prompts", prompts_module)
ai_strategy_pkg.prompts = prompts_module

# 加载 performance_monitor 模块
spec_pm = importlib.util.spec_from_file_location(
    "ai.strategy.performance_monitor", _strategy_dir / "performance_monitor.py"
)
assert spec_pm is not None and spec_pm.loader is not None, "无法加载 performance_monitor 模块"
pm_module = importlib.util.module_from_spec(spec_pm)
_inject("ai.strategy.performance_monitor", pm_module)
spec_pm.loader.exec_module(pm_module)
ai_strategy_pkg.performance_monitor = pm_module

# 模拟 thinking_chain 模块
thinking_chain_module = type(sys)("ai.strategy.thinking_chain")


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
                {
                    "key": "analyze_requirement",
                    "title": "分析需求",
                    "description": "分析用户策略需求",
                },
                {
                    "key": "design_strategy",
                    "title": "设计策略",
                    "description": "设计交易策略逻辑",
                },
                {
                    "key": "generate_code",
                    "title": "生成代码",
                    "description": "生成策略代码",
                },
                {"key": "optimize", "title": "优化完善", "description": "优化代码结构"},
            ],
            "is_active": True,
        }


thinking_chain_module.ThinkingChainManager = MockThinkingChainManager
_inject("ai.strategy.thinking_chain", thinking_chain_module)
ai_strategy_pkg.thinking_chain = thinking_chain_module

# 加载 strategy_generator 模块（用包限定名，使 from .xxx 相对 import 生效）
spec_sg = importlib.util.spec_from_file_location(
    "ai.strategy.strategy_generator", _strategy_dir / "strategy_generator.py"
)
assert spec_sg is not None and spec_sg.loader is not None, "无法加载 strategy_generator 模块"
sg_module = importlib.util.module_from_spec(spec_sg)

# 注册 strategy_generator 模块
_inject("ai.strategy.strategy_generator", sg_module)

# 执行模块
spec_sg.loader.exec_module(sg_module)
ai_strategy_pkg.strategy_generator = sg_module

# 导出需要的类和函数
StrategyGenerator = sg_module.StrategyGenerator
StrategyGenerationError = sg_module.StrategyGenerationError
APIAuthenticationError = sg_module.APIAuthenticationError
APIConnectionError = sg_module.APIConnectionError
APIRateLimitError = sg_module.APIRateLimitError
ResponseParseError = sg_module.ResponseParseError
strip_code_from_content = sg_module.strip_code_from_content


class FakeBackend:
    """模拟 axon_quant LLMBackend 的同步接口（chat / stream_chat）

    返回原始 axon 格式；可通过 chat_error / stream_error 注入 RuntimeError，
    用于测试业务代码基于 classify_llm_error 的错误分类逻辑。
    """

    def __init__(self, chat_resp=None, stream_deltas=None):
        self.chat_resp = chat_resp or {
            "content": "```python\nclass Demo:\n    pass\n```",
            "reasoning_content": "",
            "finish_reason": "Stop",
            "prompt_tokens": 1,
            "completion_tokens": 2,
            "total_tokens": 3,
        }
        self.stream_deltas = stream_deltas or []
        self.chat_error = None
        self.stream_error = None

    def chat(self, messages):
        if self.chat_error is not None:
            raise self.chat_error
        return self.chat_resp

    def stream_chat(self, messages):
        if self.stream_error is not None:
            raise self.stream_error
        return self.stream_deltas


class TestStrategyGeneratorInit:
    """测试 StrategyGenerator 初始化"""

    def test_init_with_required_params(self):
        """测试使用必需参数初始化"""
        with patch("ai.strategy.strategy_generator.create_llm_backend", return_value=FakeBackend()):
            generator = StrategyGenerator(api_key="test-key")

            assert generator.api_key == "test-key"
            assert generator.api_host == StrategyGenerator.DEFAULT_API_HOST
            assert generator.model_id == StrategyGenerator.DEFAULT_MODEL
            assert generator.temperature == StrategyGenerator.DEFAULT_TEMPERATURE

    def test_init_with_all_params(self):
        """测试使用所有参数初始化"""
        with patch("ai.strategy.strategy_generator.create_llm_backend", return_value=FakeBackend()):
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
        with patch("ai.strategy.strategy_generator.create_llm_backend", return_value=FakeBackend()):
            generator = StrategyGenerator(
                api_key="test-key",
                api_host="https://api.example.com/",
            )

            # 内部会去除尾部斜杠（/v1 由 create_llm_backend 补齐）
            assert generator.api_host == "https://api.example.com"

    def test_init_creates_llm_backend(self):
        """测试初始化创建 axon LLM backend"""
        with patch("ai.strategy.strategy_generator.create_llm_backend", return_value=FakeBackend()) as mock_create:
            StrategyGenerator(api_key="test-key")

            mock_create.assert_called_once()
            call_kwargs = mock_create.call_args.kwargs
            assert call_kwargs["api_key"] == "test-key"
            assert call_kwargs["base_url"] == StrategyGenerator.DEFAULT_API_HOST
            assert call_kwargs["model"] == StrategyGenerator.DEFAULT_MODEL
            assert call_kwargs["max_tokens"] == StrategyGenerator.DEFAULT_MAX_TOKENS
            assert call_kwargs["timeout_secs"] == int(StrategyGenerator.DEFAULT_TIMEOUT)


class TestStrategyGeneratorCodeExtraction:
    """测试 StrategyGenerator 代码提取功能"""

    @pytest.fixture
    def generator(self):
        """创建测试用的生成器实例"""
        with patch("ai.strategy.strategy_generator.create_llm_backend", return_value=FakeBackend()):
            return StrategyGenerator(api_key="test-key")

    def test_extract_code_with_python_markers(self, generator):
        """测试提取带 python 标记的代码块"""
        content = """Some text
```python
class MyStrategy:
    pass
```
More text"""

        code = generator._extract_code(content)
        assert "class MyStrategy:" in code
        assert "```" not in code

    def test_extract_code_with_generic_markers(self, generator):
        """测试提取通用代码块"""
        content = """Some text
```
def hello():
    pass
```
More text"""

        code = generator._extract_code(content)
        assert "def hello():" in code
        assert "```" not in code

    def test_extract_code_single_line(self, generator):
        """测试提取单行代码块"""
        content = "```python\nclass Test: pass\n```"

        code = generator._extract_code(content)
        assert "class Test: pass" in code

    def test_extract_code_python_indicators(self, generator):
        """测试通过 Python 关键字识别代码"""
        content = """class MyStrategy:
    def __init__(self):
        pass"""

        code = generator._extract_code(content)
        assert "class MyStrategy:" in code

    def test_extract_code_import_indicator(self, generator):
        """测试通过 import 关键字识别代码"""
        content = """import numpy as np
from typing import List"""

        code = generator._extract_code(content)
        assert "import numpy" in code

    def test_extract_code_def_indicator(self, generator):
        """测试通过 def 关键字识别代码"""
        content = """def calculate():
    return 42"""

        code = generator._extract_code(content)
        assert "def calculate():" in code

    def test_extract_code_comment_indicator(self, generator):
        """测试通过注释识别代码"""
        content = """# This is a comment
class Strategy:
    pass"""

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
        content = """```python
first block
```
```python
second block
```"""

        code = generator._extract_code(content)
        assert "first block" in code
        assert "second block" not in code


class TestStrategyGeneratorResponseParsing:
    """测试 StrategyGenerator 响应解析功能"""

    @pytest.fixture
    def generator(self):
        """创建测试用的生成器实例"""
        with patch("ai.strategy.strategy_generator.create_llm_backend", return_value=FakeBackend()):
            return StrategyGenerator(api_key="test-key")

    def test_parse_response_success(self, generator):
        """测试成功解析响应"""
        content = """```python
class MyStrategy:
    def __init__(self):
        pass
```"""

        result = generator._parse_response(content)

        assert result["success"] is True
        assert "class MyStrategy:" in result["code"]
        # 全代码输入清洗后无说明文字，下发默认文案
        assert result["raw_content"] == "策略代码已生成，请查看下方代码。"
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
        """无法提取代码时兜底返回整个 content 当 code，content 和 code 相同 → 默认文案"""
        content = "Just plain text without any code blocks"

        result = generator._parse_response(content)

        assert result["success"] is True
        assert result["code"] == content
        assert result["raw_content"] == "策略代码已生成，请查看下方代码。"

    def test_parse_response_strips_code_and_keeps_explanation(self, generator):
        """说明文字 + 代码围栏：正文只保留说明文字"""
        content = (
            "该策略使用 RSI 超买超卖信号进行均值回归交易。\n"
            "核心参数为 overbought 和 oversold。\n\n"
            "```python\n"
            "class RsiStrategy(BaseStrategy):\n"
            "    def __init__(self):\n"
            "        pass\n"
            "```\n"
        )

        result = generator._parse_response(content)

        assert result["success"] is True
        assert "class RsiStrategy" in result["code"]
        assert "RSI 超买超卖" in result["raw_content"]
        assert "核心参数" in result["raw_content"]
        assert "```" not in result["raw_content"]  # 围栏标记已清除
        assert "class RsiStrategy" not in result["raw_content"]

    def test_parse_response_with_malformed_fences(self, generator):
        """围栏错乱下：_extract_code 抓第一个围栏 body，strip 据此剔除所有重复代码残留"""
        # _extract_code 会优先匹配 pattern2 的第一个 ``` ``` 围栏 body 作为 code；
        # strip 函数拿到这个 code 后，content 中裸行 + 围栏内所有匹配行都应被剔除
        content = (
            "策略逻辑概述...\n"
            "\n"
            # 裸代码（2 行匹配 → 裸段落阈值 2 触发剔除）
            "class RsiOverboughtOversoldStrategy(BaseStrategy):\n"
            "    def __init__(self):\n"
            "\n"
            # 第一个无语言围栏 —— _extract_code 抓这个 body 作为 code
            "```\n"
            "class RsiOverboughtOversoldStrategy(BaseStrategy):\n"
            "    def __init__(self):\n"
            "        pass\n"
            "```\n"
            "\n"
            # 第二个 python 围栏（多行匹配 → 剔除）
            "```python\n"
            "class RsiOverboughtOversoldStrategy(BaseStrategy):\n"
            "    def __init__(self):\n"
            "        pass\n"
            "```\n"
        )

        result = generator._parse_response(content)

        assert result["success"] is True
        # 正文只剩概述
        assert result["raw_content"].strip() == "策略逻辑概述..."


class TestStripCodeFromContent:
    """直接测试 strip_code_from_content 的剔除逻辑。

    新策略：无围栏 → 纯代码场景 → 默认文案；有围栏 → 删所有围栏块留说明。
    这个分叉比 python_indicators 判定更干净——纯代码场景下不可能有说明文字，
    有说明文字就一定有 Markdown 标记（围栏/标题/列表）。
    """

    def test_empty_content_passthrough(self):
        assert strip_code_from_content("", "class S: pass") == ""

    def test_pure_code_no_fence_returns_default(self):
        """真实样本场景：模型输出纯 Python，无围栏，content 全是代码"""
        code = (
            "from __future__ import annotations\nclass RsiStrategy(BaseStrategy):\n    def on_bar(self):\n        pass"
        )
        # content 和 code 完全一样——无围栏，纯代码
        assert strip_code_from_content(code, code) == "策略代码已生成，请查看下方代码。"

    def test_normal_fence_removed_explanation_kept(self):
        content = (
            "这是一个 RSI 策略。\n\n"
            "```python\n"
            "class RsiStrategy(BaseStrategy):\n"
            "    def __init__(self):\n"
            "        pass\n"
            "```\n"
        )
        code = "class RsiStrategy(BaseStrategy):\n    def __init__(self):\n        pass"

        result = strip_code_from_content(content, code)

        assert "RSI 策略" in result
        assert "```" not in result
        assert "class RsiStrategy" not in result

    def test_noise_bare_code_with_fence_present(self):
        """围栏外还有裸代码——但模型既然输出了围栏说明，就保留围栏清洗，
        裸代码可能是说明里的示例代码片段，保守保留"""
        content = "策略说明。\n\n```python\nclass RsiStrategy:\n    pass\n```\n"
        code = "class RsiStrategy:\n    pass"
        result = strip_code_from_content(content, code)
        assert "策略说明" in result
        assert "```" not in result

    def test_docstring_fragment_fence_removed(self):
        """docstring 被切成无语言围栏碎片——有围栏就删"""
        content = "策略概述。\n\n```\n    交易逻辑：RSI <= oversold 开多。\n```\n"
        code = 'class RsiStrategy(BaseStrategy):\n    """策略。\n\n    交易逻辑：RSI <= oversold 开多。\n    """'

        result = strip_code_from_content(content, code)

        assert "策略概述" in result
        assert "```" not in result
        assert "交易逻辑" not in result

    def test_single_line_code_reference_preserved(self):
        """说明里的行内 ```code``` 也会被删（围栏删除覆盖所有 fence 变体），
        但说明文字本身保留"""
        content = (
            "使用 rsi 模块做计算。\n\n"
            "```python\n"
            "class RsiStrategy:\n"
            "    def __init__(self):\n"
            "        self.rsi = 14\n"
            "```\n"
        )
        code = "class RsiStrategy:\n    def __init__(self):\n        self.rsi = 14"

        result = strip_code_from_content(content, code)

        assert "rsi 模块" in result
        assert "```" not in result

    def test_repeated_complete_code_block_stripped(self):
        """完整代码重复出现两遍（两个围栏）"""
        content = (
            "策略概述。\n\n"
            "```python\n"
            "class RsiStrategy:\n"
            "    def run(self):\n"
            "        pass\n"
            "```\n"
            "\n"
            "```python\n"
            "class RsiStrategy:\n"
            "    def run(self):\n"
            "        pass\n"
            "```\n"
        )
        code = "class RsiStrategy:\n    def run(self):\n        pass"

        result = strip_code_from_content(content, code)

        assert "策略概述" in result
        assert result.count("```") == 0

    def test_fence_deletion_leaves_default_when_nothing_left(self):
        """模型输出被围栏包裹的代码 + 围栏前只有空白 → 清洗后为空 → 默认文案"""
        content = "```python\nclass Foo:\n    pass\n```"
        result = strip_code_from_content(content, "class Foo:\n    pass")
        assert result == "策略代码已生成，请查看下方代码。"


class TestStrategyGeneratorErrorHandling:
    """测试 StrategyGenerator 错误处理"""

    @pytest.fixture
    def generator(self):
        """创建测试用的生成器实例"""
        with patch("ai.strategy.strategy_generator.create_llm_backend", return_value=FakeBackend()):
            return StrategyGenerator(api_key="test-key")

    @pytest.mark.asyncio
    async def test_generate_strategy_stream_authentication_error(self, generator):
        """测试流式生成时认证错误处理"""
        generator._backend.stream_error = RuntimeError("auth error: invalid key")

        chunks = []
        async for chunk in generator.generate_strategy_stream("test requirement"):
            chunks.append(chunk)

        # 现在会返回思维链事件 + 错误事件
        assert len(chunks) >= 2
        # 最后一个chunk应该是错误
        assert chunks[-1]["type"] == "error"
        assert chunks[-1]["error_code"] == "api_authentication_error"
        assert "API密钥无效" in chunks[-1]["error"]
        # 检查思维链事件
        thinking_chain_chunks = [c for c in chunks if c["type"] == "thinking_chain"]
        assert len(thinking_chain_chunks) >= 1

    @pytest.mark.asyncio
    async def test_generate_strategy_stream_rate_limit_error(self, generator):
        """测试流式生成时速率限制错误处理"""
        generator._backend.stream_error = RuntimeError("rate limited (retry_after=3s)")

        chunks = []
        async for chunk in generator.generate_strategy_stream("test requirement"):
            chunks.append(chunk)

        # 现在会返回思维链事件 + 错误事件
        assert len(chunks) >= 2
        # 最后一个chunk应该是错误
        assert chunks[-1]["type"] == "error"
        assert chunks[-1]["error_code"] == "api_rate_limit_error"
        assert "请求过于频繁" in chunks[-1]["error"]

    @pytest.mark.asyncio
    async def test_generate_strategy_stream_timeout_error(self, generator):
        """测试流式生成时超时错误处理"""
        generator._backend.stream_error = RuntimeError("network error: request timeout")

        chunks = []
        async for chunk in generator.generate_strategy_stream("test requirement"):
            chunks.append(chunk)

        # 现在会返回思维链事件 + 错误事件
        assert len(chunks) >= 2
        # 最后一个chunk应该是错误
        assert chunks[-1]["type"] == "error"
        assert chunks[-1]["error_code"] == "api_connection_error"
        assert "超时" in chunks[-1]["error"]

    @pytest.mark.asyncio
    async def test_generate_strategy_stream_connection_error(self, generator):
        """测试流式生成时连接错误处理"""
        generator._backend.stream_error = RuntimeError("network error: connection reset")

        chunks = []
        async for chunk in generator.generate_strategy_stream("test requirement"):
            chunks.append(chunk)

        # 现在会返回思维链事件 + 错误事件
        assert len(chunks) >= 2
        # 最后一个chunk应该是错误
        assert chunks[-1]["type"] == "error"
        assert chunks[-1]["error_code"] == "api_connection_error"

    @pytest.mark.asyncio
    async def test_generate_strategy_stream_generic_exception(self, generator):
        """测试流式生成时通用异常处理"""
        # 非 RuntimeError 的异常走通用分支
        generator._backend.stream_error = ValueError("Unexpected error")

        chunks = []
        async for chunk in generator.generate_strategy_stream("test requirement"):
            chunks.append(chunk)

        # 现在会返回思维链事件 + 错误事件
        assert len(chunks) >= 2
        # 最后一个chunk应该是错误
        assert chunks[-1]["type"] == "error"
        assert chunks[-1]["error_code"] == "generation_failed"
        assert "策略生成失败" in chunks[-1]["error"]

    @pytest.mark.asyncio
    async def test_generate_strategy_stream_empty_content_truncated(self, generator):
        """推理模型思维链耗尽 token 预算：只有 reasoning + done(Length)，正文为空 → error 事件"""
        generator._backend.stream_deltas = [
            {"type": "reasoning", "content": "思考中..."},
            {"type": "done", "finish_reason": "Length"},
        ]

        chunks = []
        async for chunk in generator.generate_strategy_stream("test requirement"):
            chunks.append(chunk)

        # 不应出现 done 事件（避免前端误显示成功）
        assert all(c["type"] != "done" for c in chunks)
        assert chunks[-1]["type"] == "error"
        assert chunks[-1]["error_code"] == "empty_response"
        assert "截断" in chunks[-1]["error"]

    @pytest.mark.asyncio
    async def test_generate_strategy_stream_salvage_code_from_reasoning(self, generator):
        """正文为空但 reasoning 里有完整代码块：兜底提取并正常返回 done"""
        generator._backend.stream_deltas = [
            {"type": "reasoning", "content": "先写一版草稿：\n```python\nclass Draft:\n    pass\n```\n"},
            {
                "type": "reasoning",
                "content": "最终版：\n```python\nclass Final(BaseStrategy):\n    pass\n```\n",
            },
            {"type": "done", "finish_reason": "Stop"},
        ]

        chunks = []
        async for chunk in generator.generate_strategy_stream("test requirement"):
            chunks.append(chunk)

        done = chunks[-1]
        assert done["type"] == "done"
        # 取最后一个含 BaseStrategy 的代码块（草稿版被跳过）
        assert "class Final(BaseStrategy)" in done["code"]
        assert done["metadata"]["from_reasoning"] is True

    @pytest.mark.asyncio
    async def test_generate_strategy_stream_success_metadata(self, generator):
        """正常返回时 done 事件带 code/raw_content 与归一化 finish_reason"""
        generator._backend.stream_deltas = [
            {"type": "content", "content": "```python\nclass S:\n    pass\n```"},
            {"type": "done", "finish_reason": "Stop"},
        ]

        chunks = []
        async for chunk in generator.generate_strategy_stream("test requirement"):
            chunks.append(chunk)

        done = chunks[-1]
        assert done["type"] == "done"
        assert done["code"]
        assert done["raw_content"]
        assert done["metadata"]["finish_reason"] == "stop"

    def test_generate_strategy_authentication_error(self, generator):
        """测试同步生成时认证错误处理"""
        generator._backend.chat_error = RuntimeError("auth error: invalid key")

        with pytest.raises(APIAuthenticationError) as exc_info:
            generator.generate_strategy("test requirement")

        assert exc_info.value.error_code == "api_authentication_error"
        assert "API密钥无效" in exc_info.value.message

    def test_generate_strategy_rate_limit_error(self, generator):
        """测试同步生成时速率限制错误处理"""
        generator._backend.chat_error = RuntimeError("rate limited (retry_after=3s)")

        with pytest.raises(APIRateLimitError) as exc_info:
            generator.generate_strategy("test requirement")

        assert exc_info.value.error_code == "api_rate_limit_error"
        assert "请求过于频繁" in exc_info.value.message

    def test_generate_strategy_timeout_error(self, generator):
        """测试同步生成时超时错误处理"""
        generator._backend.chat_error = RuntimeError("network error: request timeout")

        with pytest.raises(APIConnectionError) as exc_info:
            generator.generate_strategy("test requirement")

        assert exc_info.value.error_code == "api_connection_error"
        assert "超时" in exc_info.value.message

    def test_generate_strategy_connection_error(self, generator):
        """测试同步生成时连接错误处理"""
        generator._backend.chat_error = RuntimeError("network error: connection reset")

        with pytest.raises(APIConnectionError) as exc_info:
            generator.generate_strategy("test requirement")

        assert exc_info.value.error_code == "api_connection_error"

    def test_generate_strategy_generic_error(self, generator):
        """测试同步生成时通用异常处理（非 RuntimeError 走 generation_failed）"""
        generator._backend.chat_error = ValueError("Unexpected error")

        with pytest.raises(StrategyGenerationError) as exc_info:
            generator.generate_strategy("test requirement")

        assert exc_info.value.error_code == "generation_failed"


class TestStrategyGeneratorValidation:
    """测试 StrategyGenerator 代码验证功能"""

    @pytest.fixture
    def generator(self):
        """创建测试用的生成器实例"""
        with patch("ai.strategy.strategy_generator.create_llm_backend", return_value=FakeBackend()):
            return StrategyGenerator(api_key="test-key")

    def test_validate_code_valid(self, generator):
        """测试验证有效代码"""
        code = """class MyStrategy:
    def __init__(self):
        pass

    def on_bar(self, data):
        return data"""

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
        code = """class MyStrategy
    def __init__(self):
        pass"""

        result = generator.validate_code(code)

        assert result["valid"] is False
        assert any("语法错误" in e for e in result["errors"])

    def test_validate_code_missing_class_warning(self, generator):
        """测试验证缺少类定义的警告"""
        code = """def standalone_function():
    return 42"""

        result = generator.validate_code(code)

        # 语法正确但缺少类定义
        assert any("未找到类定义" in e for e in result["errors"])

    def test_validate_code_missing_function_warning(self, generator):
        """测试验证缺少函数定义的警告"""
        code = """x = 42"""

        result = generator.validate_code(code)

        assert any("未找到函数定义" in e for e in result["errors"])


class TestStrategyGeneratorBuildPrompt:
    """测试 StrategyGenerator 提示词构建功能"""

    @pytest.fixture
    def generator(self):
        """创建测试用的生成器实例"""
        with patch("ai.strategy.strategy_generator.create_llm_backend", return_value=FakeBackend()):
            return StrategyGenerator(api_key="test-key")

    def test_build_prompt_with_default_vars(self, generator):
        """测试使用默认变量构建提示词"""
        with patch.object(generator._prompt_manager, "render") as mock_render:
            mock_render.return_value = "rendered prompt"

            result = generator._build_prompt("my requirement", PromptCategory.STRATEGY_GENERATION)

            assert result == "rendered prompt"
            mock_render.assert_called_once()
            call_kwargs = mock_render.call_args.kwargs
            assert call_kwargs["user_requirement"] == "my requirement"
            assert call_kwargs["strategy_name"] == "GeneratedStrategy"
            assert call_kwargs["symbol"] == "BTC/USDT"

    def test_build_prompt_with_custom_vars(self, generator):
        """测试使用自定义变量构建提示词"""
        with patch.object(generator._prompt_manager, "render") as mock_render:
            mock_render.return_value = "rendered prompt"

            generator._build_prompt(
                "my requirement",
                PromptCategory.STRATEGY_GENERATION,
                strategy_name="CustomStrategy",
                symbol="ETH/USDT",
                timeframe="4h",
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
        # 16384: 推理模型的思维链 token 也计入预算，4096 会被思维链耗尽导致正文为空
        assert StrategyGenerator.DEFAULT_MAX_TOKENS == 16384


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
