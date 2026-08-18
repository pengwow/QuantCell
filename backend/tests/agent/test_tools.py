"""Agent 工具测试"""

from pathlib import Path
from unittest.mock import patch

import pytest

from agent.tools.filesystem import ListDirTool, ReadFileTool, WriteFileTool
from agent.tools.registry import ToolRegistry
from agent.tools.shell import ExecTool


class TestToolRegistry:
    """测试工具注册表"""

    def test_register_and_get(self):
        registry = ToolRegistry()
        tool = ReadFileTool(Path("/tmp"))

        registry.register(tool)
        assert registry.get("read_file") == tool
        assert registry.has("read_file")

    def test_unregister(self):
        registry = ToolRegistry()
        tool = ReadFileTool(Path("/tmp"))

        registry.register(tool)
        registry.unregister("read_file")
        assert not registry.has("read_file")

    def test_get_definitions(self):
        registry = ToolRegistry()
        tool = ReadFileTool(Path("/tmp"))

        registry.register(tool)
        definitions = registry.get_definitions()
        assert len(definitions) == 1
        assert definitions[0]["function"]["name"] == "read_file"


class TestFilesystemTools:
    """测试文件系统工具"""

    @pytest.fixture
    def temp_workspace(self, tmp_path):
        return tmp_path

    @pytest.mark.asyncio
    async def test_read_file(self, temp_workspace):
        # 创建测试文件
        test_file = temp_workspace / "test.txt"
        test_file.write_text("Hello, World!")

        tool = ReadFileTool(temp_workspace)
        result = await tool.execute(path="test.txt")

        assert "Hello, World!" in result

    @pytest.mark.asyncio
    async def test_write_file(self, temp_workspace):
        tool = WriteFileTool(temp_workspace)
        result = await tool.execute(path="output.txt", content="Test content")

        assert "已写入" in result
        assert (temp_workspace / "output.txt").read_text() == "Test content"

    @pytest.mark.asyncio
    async def test_list_dir(self, temp_workspace):
        # 创建测试文件和目录
        (temp_workspace / "file1.txt").touch()
        (temp_workspace / "dir1").mkdir()

        tool = ListDirTool(temp_workspace)
        result = await tool.execute()

        assert "file1.txt" in result
        assert "dir1" in result

    @pytest.mark.asyncio
    async def test_read_file_not_found(self, temp_workspace):
        """测试读取不存在的文件"""
        tool = ReadFileTool(temp_workspace)
        result = await tool.execute(path="nonexistent.txt")

        assert "错误" in result
        assert "不存在" in result

    @pytest.mark.asyncio
    async def test_read_file_with_offset_limit(self, temp_workspace):
        """测试带偏移和限制的读取"""
        test_file = temp_workspace / "lines.txt"
        test_file.write_text("line1\nline2\nline3\nline4\nline5")

        tool = ReadFileTool(temp_workspace)
        result = await tool.execute(path="lines.txt", offset=2, limit=2)

        assert "line2" in result
        assert "line3" in result
        assert "line1" not in result

    @pytest.mark.asyncio
    async def test_write_file_creates_dirs(self, temp_workspace):
        """测试写入文件时自动创建目录"""
        tool = WriteFileTool(temp_workspace)
        result = await tool.execute(path="subdir/nested/file.txt", content="Test")

        assert "已写入" in result
        assert (temp_workspace / "subdir" / "nested" / "file.txt").read_text() == "Test"

    @pytest.mark.asyncio
    async def test_list_dir_empty(self, temp_workspace):
        """测试列出空目录"""
        empty_dir = temp_workspace / "empty"
        empty_dir.mkdir()

        tool = ListDirTool(temp_workspace)
        result = await tool.execute(path="empty")

        assert "空目录" in result

    @pytest.mark.asyncio
    async def test_list_dir_not_found(self, temp_workspace):
        """测试列出不存在的目录"""
        tool = ListDirTool(temp_workspace)
        result = await tool.execute(path="nonexistent")

        assert "错误" in result
        assert "不存在" in result


class TestShellTool:
    """测试Shell工具"""

    @pytest.fixture
    def temp_workspace(self, tmp_path):
        return tmp_path

    @pytest.mark.asyncio
    async def test_exec_simple_command(self, temp_workspace):
        """测试执行简单命令"""
        tool = ExecTool(str(temp_workspace))
        result = await tool.execute(command="echo 'Hello'")

        assert "Hello" in result
        assert "退出码: 0" in result

    @pytest.mark.asyncio
    async def test_exec_command_with_output(self, temp_workspace):
        """测试执行带输出的命令"""
        tool = ExecTool(str(temp_workspace))
        result = await tool.execute(command="ls -la")

        assert "stdout" in result
        assert "退出码" in result

    @pytest.mark.asyncio
    async def test_exec_command_error(self, temp_workspace):
        """测试执行错误命令"""
        tool = ExecTool(str(temp_workspace))
        result = await tool.execute(command="nonexistent_command_12345")

        assert "stderr" in result or "错误" in result

    @pytest.mark.asyncio
    async def test_exec_command_timeout(self, temp_workspace):
        """测试命令超时"""
        tool = ExecTool(str(temp_workspace), timeout=1)
        result = await tool.execute(command="sleep 10", timeout=1)

        assert "超时" in result


class TestToolRegistryExtended:
    """扩展的工具注册表测试"""

    def test_register_multiple_tools(self):
        """测试注册多个工具"""
        registry = ToolRegistry()

        tool1 = ReadFileTool(Path("/tmp"))
        tool2 = WriteFileTool(Path("/tmp"))
        tool3 = ListDirTool(Path("/tmp"))

        registry.register(tool1)
        registry.register(tool2)
        registry.register(tool3)

        assert len(registry) == 3
        assert registry.has("read_file")
        assert registry.has("write_file")
        assert registry.has("list_dir")

    def test_get_definitions_multiple(self):
        """测试获取多个工具定义"""
        registry = ToolRegistry()

        registry.register(ReadFileTool(Path("/tmp")))
        registry.register(WriteFileTool(Path("/tmp")))

        definitions = registry.get_definitions()

        assert len(definitions) == 2
        names = [d["function"]["name"] for d in definitions]
        assert "read_file" in names
        assert "write_file" in names

    def test_tool_names(self):
        """测试获取工具名称列表"""
        registry = ToolRegistry()

        registry.register(ReadFileTool(Path("/tmp")))
        registry.register(WriteFileTool(Path("/tmp")))

        names = registry.tool_names

        assert "read_file" in names
        assert "write_file" in names

    @pytest.mark.asyncio
    async def test_execute_tool(self, tmp_path):
        """测试执行工具"""
        registry = ToolRegistry()

        # 创建测试文件
        test_file = tmp_path / "test.txt"
        test_file.write_text("Test content")

        registry.register(ReadFileTool(tmp_path))

        result = await registry.execute("read_file", {"path": "test.txt"})

        assert "Test content" in result

    @pytest.mark.asyncio
    async def test_execute_nonexistent_tool(self):
        """测试执行不存在的工具"""
        registry = ToolRegistry()

        result = await registry.execute("nonexistent_tool", {})

        assert "错误" in result
        assert "不存在" in result

    @pytest.mark.asyncio
    async def test_execute_tool_with_string_params(self, tmp_path):
        """测试使用字符串参数执行工具"""
        registry = ToolRegistry()

        test_file = tmp_path / "test.txt"
        test_file.write_text("Test content")

        registry.register(ReadFileTool(tmp_path))

        # 传入JSON字符串
        result = await registry.execute("read_file", '{"path": "test.txt"}')

        assert "Test content" in result

    @pytest.mark.asyncio
    async def test_execute_tool_with_invalid_params(self, tmp_path):
        """测试使用无效参数执行工具"""
        registry = ToolRegistry()
        registry.register(ReadFileTool(tmp_path))

        # 缺少必需参数
        result = await registry.execute("read_file", {})

        assert "错误" in result

    def test_contains(self):
        """测试__contains__方法"""
        registry = ToolRegistry()
        registry.register(ReadFileTool(Path("/tmp")))

        assert "read_file" in registry
        assert "write_file" not in registry

    def test_len(self):
        """测试__len__方法"""
        registry = ToolRegistry()

        assert len(registry) == 0

        registry.register(ReadFileTool(Path("/tmp")))
        assert len(registry) == 1


class TestWebTools:
    """测试Web工具（使用mock）"""

    @pytest.mark.asyncio
    async def test_web_search_no_api_key(self):
        """测试无API密钥的搜索"""
        with patch(
            "agent.tools.web.WebSearchTool.api_key",
            new_callable=lambda: property(lambda self: ""),
        ):
            from agent.tools.web import WebSearchTool

            tool = WebSearchTool()
            result = await tool.execute(query="test")

            assert "API key" in result or "未配置" in result

    @pytest.mark.asyncio
    async def test_web_fetch_invalid_url(self):
        """测试无效URL获取"""
        from agent.tools.web import WebFetchTool

        tool = WebFetchTool()
        result = await tool.execute(url="not-a-url")

        assert "错误" in result or "error" in result.lower()

    @pytest.mark.asyncio
    async def test_web_fetch_nonexistent_domain(self):
        """测试不存在的域名获取"""
        from agent.tools.web import WebFetchTool

        tool = WebFetchTool()
        result = await tool.execute(url="https://nonexistent-domain-12345.com")

        assert "错误" in result or "error" in result.lower()


class TestTradingTools:
    """测试交易工具（使用mock）"""

    @pytest.mark.asyncio
    async def test_get_news_no_api_key(self, monkeypatch):
        """测试无API密钥的新闻获取"""
        monkeypatch.delenv("NEWSAPI_KEY", raising=False)

        from agent.tools.trading.news import GetNewsTool

        tool = GetNewsTool()
        result = await tool.execute()

        assert "API" in result or "未配置" in result

    @pytest.mark.asyncio
    async def test_list_strategies_no_db(self):
        """测试无数据库时列出策略"""
        from agent.tools.trading.strategy import ListStrategiesTool

        tool = ListStrategiesTool()

        # Mock数据库导入失败
        with patch("builtins.__import__", side_effect=ImportError("No module")):
            result = await tool.execute()

            assert "错误" in result
