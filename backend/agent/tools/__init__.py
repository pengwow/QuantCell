"""Agent 工具模块 - 统一工具注册入口"""

from pathlib import Path
from typing import List, Dict, Any
from .registry import ToolRegistry
from .base import Tool


def _discover_tool_classes() -> List[type[Tool]]:
    """自动发现 tools/ 目录下所有工具类"""
    tool_classes = []
    tools_dir = Path(__file__).parent
    
    # 需要扫描的子目录（排除 __pycache__ 和 base.py）
    exclude_dirs = {"__pycache__", "trading"}
    
    for py_file in tools_dir.rglob("*.py"):
        # 跳过特殊文件
        if py_file.name.startswith("_") or py_file.name == "base.py":
            continue
        
        # 跳过排除的目录
        rel_path = py_file.relative_to(tools_dir)
        if any(part in exclude_dirs for part in rel_path.parts):
            continue
            
        try:
            # 构建模块路径
            module_parts = list(rel_path.with_suffix("").parts)
            module_name = "agent.tools." + ".".join(module_parts)
            
            # 动态导入模块
            import importlib
            mod = importlib.import_module(module_name)
            
            # 查找 Tool 子类
            for attr_name in dir(mod):
                attr = getattr(mod, attr_name)
                if (isinstance(attr, type) and 
                    issubclass(attr, Tool) and 
                    attr is not Tool and
                    not getattr(attr, "_is_abstract", False)):
                    tool_classes.append(attr)
                    
        except Exception as e:
            pass  # 跳过无法导入的模块
    
    return tool_classes


def create_registry(workspace: Path | str | None = None, **kwargs) -> ToolRegistry:
    """
    创建并初始化工具注册表（自动注册所有工具）
    
    Args:
        workspace: 工作空间路径
        allowed_dir: 允许访问的根目录（默认为 workspace）
        **kwargs: 其他参数（如 working_dir, timeout 等）
    
    Returns:
        已注册所有工具的 ToolRegistry 实例
    
    使用示例:
        from agent.tools import create_registry
        
        registry = create_registry(workspace="/path/to/workspace")
        
        # 允许访问所有路径
        registry = create_registry(allowed_dir=Path("/"))
    """
    if workspace and isinstance(workspace, str):
        workspace = Path(workspace)
    elif workspace is None:
        from pathlib import Path
        workspace = Path(__file__).resolve().parent.parent.parent / "agent_workspace"
    
    # 获取 allowed_dir 参数（用于文件系统工具的安全限制）
    allowed_dir = kwargs.pop("allowed_dir", None) or workspace
    
    registry = ToolRegistry()
    
    # 自动发现并实例化所有工具
    tool_classes = _discover_tool_classes()
    
    for cls in tool_classes:
        try:
            # 根据工具类型传递不同的构造参数
            name = cls.__name__
            
            if name in ("ReadFileTool", "WriteFileTool", "ListDirTool"):
                tool = cls(workspace=workspace, allowed_dir=allowed_dir)
            elif name == "ExecTool":
                tool = cls(
                    working_dir=str(kwargs.get("working_dir") or workspace),
                    timeout=kwargs.get("timeout", 60),
                )
            elif name in ("WebSearchTool", "WebFetchTool"):
                tool = cls()
            else:
                # 尝试无参构造或带 workspace 参数
                try:
                    tool = cls()
                except TypeError:
                    tool = cls(workspace=workspace)
            
            registry.register(tool)
            
        except Exception as e:
            pass  # 跳过无法实例化的工具
    
    return registry


def get_tool_definitions(workspace: Path | str | None = None, **kwargs) -> List[Dict[str, Any]]:
    """
    获取所有工具定义（OpenAI 格式）
    
    Args:
        workspace: 工作空间路径
        **kwargs: 其他参数
    
    Returns:
        工具定义列表
    """
    return create_registry(workspace, **kwargs).get_definitions()


def get_tool_list(workspace: Path | str | None = None, **kwargs) -> List[Dict[str, str]]:
    """
    获取工具列表（名称和描述）
    
    Args:
        workspace: 工作空间路径
        **kwargs: 其他参数
    
    Returns:
        [{"name": "...", "description": "..."}, ...]
    """
    registry = create_registry(workspace, **kwargs)
    return [
        {
            "name": name,
            "description": tool.description,
        }
        for name, tool in registry._tools.items()
    ]


# 便捷导出
__all__ = [
    "Tool",
    "ToolRegistry",
    "create_registry",
    "get_tool_definitions",
    "get_tool_list",
]
