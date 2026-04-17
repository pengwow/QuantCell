"""Agent 工具测试"""

import pytest
from pathlib import Path

from agent.tools.base import Tool
from agent.tools.registry import ToolRegistry
from agent.tools.filesystem import ReadFileTool, WriteFileTool, ListDirTool


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
