"""工具注册表 - 管理所有可用工具"""

import time
from typing import TYPE_CHECKING, Any

from utils.logger import LogType, get_logger

from ..core.audit import agent_caller, record_tool_call

if TYPE_CHECKING:
    from .base import Tool

logger = get_logger(__name__, LogType.APPLICATION)


class ToolRegistry:
    """
    工具注册表

    支持动态注册和执行工具
    """

    def __init__(self, allow_dangerous: bool = False):
        self._tools: dict[str, Tool] = {}
        # 信任模式（P2-06）：True 时 dangerous 工具放行，等价于人工确认已由
        # 部署方统一给予；默认 False，dangerous 工具一律拦截
        self.allow_dangerous = allow_dangerous

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

            # P2-06 风险拦截（先于参数校验，保证危险工具无论参数对错都不执行）：
            # 1. dangerous 工具仅在信任模式（allow_dangerous）下放行，否则视为等
            #    待人工确认，不执行；
            # 2. 只读 scope 的 Agent Token（外部调用方）不能执行任何有副作用的工具。
            caller = agent_caller.get()
            caller_scope = caller[2] if caller else "full"
            if tool.risk_level == "dangerous" and not self.allow_dangerous:
                record_tool_call(name, params, "blocked_approval")
                return (
                    f"工具 '{name}' 被标记为危险操作，需要人工确认后才能执行。"
                    "请改用其他方式，或由用户手动完成该操作。" + _HINT
                )
            if tool.risk_level in ("write", "dangerous") and caller_scope == "read":
                record_tool_call(name, params, "blocked_scope")
                return f"错误: 当前令牌为只读权限，不允许执行有副作用的工具 '{name}'。" + _HINT

            errors = tool.validate_params(params)
            if errors:
                record_tool_call(name, params, "invalid_params")
                return f"错误: 工具 '{name}' 参数无效: " + "; ".join(errors) + _HINT

            logger.debug(f"[ToolRegistry] 执行工具 {name}, 参数: {params}")
            start_time = time.time()

            result = await tool.execute(**params)

            elapsed = time.time() - start_time
            logger.info(f"[ToolRegistry] 工具 {name} 执行完成, 耗时: {elapsed:.2f}s")
            record_tool_call(name, params, "success", duration_ms=int(elapsed * 1000))

            if isinstance(result, str) and result.startswith("错误"):
                return result + _HINT
            return result
        except Exception as e:
            logger.error(f"[ToolRegistry] 工具 {name} 执行异常: {type(e).__name__}: {e}")
            record_tool_call(name, params, "error")
            return f"执行 {name} 时出错: {e!s}" + _HINT

    @property
    def tool_names(self) -> list[str]:
        """获取所有工具名称"""
        return list(self._tools.keys())

    def __len__(self) -> int:
        return len(self._tools)

    def __contains__(self, name: str) -> bool:
        return name in self._tools
