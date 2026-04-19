"""文件系统工具 - 读写文件、列出目录"""

from pathlib import Path
from typing import Any

from .base import Tool


class ReadFileTool(Tool):
    """读取文件内容"""

    name = "read_file"
    description = "读取文件内容。支持文本文件，返回文件内容或错误信息。"
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "文件路径（相对于工作空间或绝对路径）"},
            "offset": {"type": "integer", "description": "起始行号（从1开始）", "minimum": 1},
            "limit": {"type": "integer", "description": "读取行数", "minimum": 1, "maximum": 500},
        },
        "required": ["path"],
    }

    param_template = {
        "default_limit": {
            "type": "integer",
            "required": False,
            "default": 200,
            "env_key": None,
            "description": "默认读取行数",
            "validation": {"min": 1, "max": 500}
        }
    }

    def __init__(self, workspace: Path, allowed_dir: Path | None = None):
        self.workspace = workspace
        self.allowed_dir = allowed_dir or workspace

    def _resolve_path(self, path: str) -> Path:
        """解析并验证路径"""
        p = Path(path)
        if not p.is_absolute():
            p = self.workspace / p
        p = p.resolve()
        
        # 检查路径是否在允许范围内
        if self.allowed_dir and not str(p).startswith(str(self.allowed_dir.resolve())):
            raise ValueError(f"路径 {path} 超出允许范围")
        return p

    async def execute(self, path: str, offset: int = 1, limit: int = 200, **kwargs: Any) -> str:
        try:
            file_path = self._resolve_path(path)
            
            if not file_path.exists():
                return f"错误: 文件不存在: {path}"
            
            if not file_path.is_file():
                return f"错误: 不是文件: {path}"

            content = file_path.read_text(encoding="utf-8")
            lines = content.split("\n")
            
            # 应用 offset 和 limit
            start = offset - 1
            end = start + limit
            selected_lines = lines[start:end]
            
            result = "\n".join(selected_lines)
            if end < len(lines):
                result += f"\n\n... ({len(lines) - end} 行更多内容)"
            
            return result
        except Exception as e:
            return f"错误: 读取文件失败: {e}"


class WriteFileTool(Tool):
    """写入文件内容"""

    name = "write_file"
    description = "写入或覆盖文件内容。如果目录不存在会自动创建。"
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "文件路径"},
            "content": {"type": "string", "description": "文件内容"},
        },
        "required": ["path", "content"],
    }

    param_template = {}

    def __init__(self, workspace: Path, allowed_dir: Path | None = None):
        self.workspace = workspace
        self.allowed_dir = allowed_dir or workspace

    def _resolve_path(self, path: str) -> Path:
        p = Path(path)
        if not p.is_absolute():
            p = self.workspace / p
        p = p.resolve()
        if self.allowed_dir and not str(p).startswith(str(self.allowed_dir.resolve())):
            raise ValueError(f"路径 {path} 超出允许范围")
        return p

    async def execute(self, path: str, content: str, **kwargs: Any) -> str:
        try:
            file_path = self._resolve_path(path)
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(content, encoding="utf-8")
            return f"文件已写入: {path}"
        except Exception as e:
            return f"错误: 写入文件失败: {e}"


class ListDirTool(Tool):
    """列出目录内容"""

    name = "list_dir"
    description = "列出目录中的文件和子目录。"
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "目录路径（默认: 工作空间根目录）"},
        },
        "required": [],
    }

    param_template = {}

    def __init__(self, workspace: Path, allowed_dir: Path | None = None):
        self.workspace = workspace
        self.allowed_dir = allowed_dir or workspace

    def _resolve_path(self, path: str | None) -> Path:
        if not path:
            return self.workspace
        p = Path(path)
        if not p.is_absolute():
            p = self.workspace / p
        p = p.resolve()
        if self.allowed_dir and not str(p).startswith(str(self.allowed_dir.resolve())):
            raise ValueError(f"路径 {path} 超出允许范围")
        return p

    async def execute(self, path: str | None = None, **kwargs: Any) -> str:
        try:
            dir_path = self._resolve_path(path)
            
            if not dir_path.exists():
                return f"错误: 目录不存在: {path or '.'}"
            
            if not dir_path.is_dir():
                return f"错误: 不是目录: {path or '.'}"

            items = []
            for item in sorted(dir_path.iterdir()):
                item_type = "📁" if item.is_dir() else "📄"
                items.append(f"{item_type} {item.name}")
            
            return "\n".join(items) if items else "(空目录)"
        except Exception as e:
            return f"错误: 列出目录失败: {e}"
