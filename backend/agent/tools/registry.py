"""工具注册表 - 管理所有可用工具"""

import time
from typing import Any

from .base import Tool
from utils.logger import get_logger, LogType

logger = get_logger(__name__, LogType.APPLICATION)


class ToolRegistry:
    """
    工具注册表
    
    支持动态注册和执行工具
    """

    def __init__(self):
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        """注册工具"""
        self._tools[tool.name] = tool

    def unregister(self, name: str) -> None:
        """注销工具"""
        self._tools.pop(name, None)

    def get(self, name: str) -> Tool | None:
        """获取工具"""
        return self._tools.get(name)

    def has(self, name: str) -> bool:
        """检查工具是否存在"""
        return name in self._tools

    def get_definitions(self) -> list[dict[str, Any]]:
        """获取所有工具定义（OpenAI 格式）"""
        return [tool.to_schema() for tool in self._tools.values()]

    async def execute(self, name: str, params: dict[str, Any] | str) -> str:
        """执行指定工具"""
        _HINT = "\n\n[分析上述错误并尝试不同的方法。]"

        tool = self._tools.get(name)
        if not tool:
            return f"错误: 工具 '{name}' 不存在。可用工具: {', '.join(self.tool_names)}"

        try:
            # 处理参数：如果是字符串则解析为字典
            if isinstance(params, str):
                import json
                try:
                    params = json.loads(params)
                except json.JSONDecodeError:
                    params = {}

            if not isinstance(params, dict):
                params = {}

            errors = tool.validate_params(params)
            if errors:
                return f"错误: 工具 '{name}' 参数无效: " + "; ".join(errors) + _HINT
            
            logger.debug(f"[ToolRegistry] 执行工具 {name}, 参数: {params}")
            start_time = time.time()
            
            result = await tool.execute(**params)
            
            elapsed = time.time() - start_time
            logger.info(f"[ToolRegistry] 工具 {name} 执行完成, 耗时: {elapsed:.2f}s")
            
            if isinstance(result, str) and result.startswith("错误"):
                return result + _HINT
            return result
        except Exception as e:
            logger.error(f"[ToolRegistry] 工具 {name} 执行异常: {type(e).__name__}: {e}")
            return f"执行 {name} 时出错: {str(e)}" + _HINT

    @property
    def tool_names(self) -> list[str]:
        """获取所有工具名称"""
        return list(self._tools.keys())

    def __len__(self) -> int:
        return len(self._tools)

    def __contains__(self, name: str) -> bool:
        return name in self._tools
