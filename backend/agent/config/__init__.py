"""
Agent 工具参数配置管理模块

提供统一的工具参数存储、解析和管理功能。
支持多级优先级：数据库 > 环境变量 > 默认值

主要组件:
- ToolParamResolver: 参数解析器（运行时使用）
- ToolParamManager: 参数管理器（CRUD操作）
- get_tool_template / get_all_tools: 模板查询接口
"""

from agent.config.tool_params import ToolParamResolver
from agent.config.manager import ToolParamManager
from agent.config.templates import get_tool_template, get_all_tools

__all__ = [
    "ToolParamResolver",
    "ToolParamManager",
    "get_tool_template",
    "get_all_tools",
]
