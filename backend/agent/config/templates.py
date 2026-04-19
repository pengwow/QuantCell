"""
参数模板注册与发现机制

自动扫描工具类并提取 param_template 属性，
提供统一的模板查询接口。

使用示例:
    from agent.config.templates import get_tool_template, get_all_tools
    
    # 获取单个工具的参数模板
    template = get_tool_template("web_search")
    
    # 获取所有工具的参数模板
    all_templates = get_all_tools()
    
    # 获取单个参数的定义
    api_key_def = get_tool_template("web_search", "api_key")
"""

import importlib
import inspect
from pathlib import Path
from typing import Any, Dict, Optional, Type
from utils.logger import get_logger, LogType

logger = get_logger(__name__, LogType.APPLICATION)

# 模块缓存
_template_cache: Optional[Dict[str, Dict[str, Any]]] = None
_tools_dir = Path(__file__).resolve().parent.parent / "tools"


def _discover_tool_classes() -> list[Type]:
    """
    扫描 tools 目录，发现所有 Tool 子类
    
    Returns:
        Tool 子类列表
    """
    tool_classes = []
    
    if not _tools_dir.exists():
        logger.warning(f"工具目录不存在: {_tools_dir}")
        return tool_classes
    
    for file_path in _tools_dir.rglob("*.py"):
        if file_path.name.startswith("_"):
            continue
        
        try:
            # 修复：正确计算模块路径
            # _tools_dir = agent/tools, 需要得到 agent/tools/web.py -> agent.tools.web
            module_rel_path = file_path.relative_to(_tools_dir.parent.parent)
            module_name = (
                str(module_rel_path.with_suffix("")).replace("/", ".").replace("\\", ".")
            )
            
            module = importlib.import_module(module_name)
            
            for attr_name, attr_value in inspect.getmembers(module, inspect.isclass):
                if (
                    issubclass(attr_value, object)
                    and hasattr(attr_value, "name")
                    and hasattr(attr_value, "param_template")
                    and attr_value.name
                ):
                    tool_classes.append(attr_value)
                    logger.debug(f"发现工具类: {attr_name} (from {module_name})")
                    
        except Exception as e:
            logger.debug(f"扫描工具类失败 {file_path}: {e}")
            continue
    
    logger.info(f"扫描完成: 发现 {len(tool_classes)} 个工具类")
    return tool_classes


def _load_templates() -> Dict[str, Dict[str, Any]]:
    """
    加载或刷新所有工具的参数模板
    
    Returns:
        {tool_name: {param_name: param_definition}}
    """
    global _template_cache
    
    templates: Dict[str, Dict[str, Any]] = {}
    
    tool_classes = _discover_tool_classes()
    
    for cls in tool_classes:
        tool_name = cls.name
        if not tool_name or tool_name in templates:
            continue
            
        param_template = getattr(cls, "param_template", None)
        if isinstance(param_template, dict):
            templates[tool_name] = param_template
            logger.debug(f"加载工具参数模板: {tool_name} ({len(param_template)} 个参数)")
    
    _template_cache = templates
    logger.info(f"已加载 {len(templates)} 个工具的参数模板")
    
    return templates


def get_tool_template(tool_name: str, param_name: Optional[str] = None) -> Any:
    """
    获取工具的参数模板
    
    Args:
        tool_name: 工具名称 (如 "web_search")
        param_name: 可选，参数名称。如果提供，只返回该参数的定义
    
    Returns:
        如果提供 param_name: 返回单个参数定义 (dict 或 None)
        如果不提供: 返回该工具的所有参数模板 (dict 或 {})
    """
    if _template_cache is None:
        _load_templates()
    
    tool_template = (_template_cache or {}).get(tool_name)
    
    if tool_template is None:
        if param_name:
            return None
        return {}
    
    if param_name:
        return tool_template.get(param_name)
    
    return tool_template


def get_all_tools() -> Dict[str, Dict[str, Any]]:
    """
    获取所有已注册工具的参数模板
    
    Returns:
        {tool_name: {param_name: param_definition}}
    """
    if _template_cache is None:
        _load_templates()
    
    return _template_cache or {}


def clear_cache():
    """
    清除模板缓存（用于测试或动态重载）
    """
    global _template_cache
    _template_cache = None
    logger.debug("参数模板缓存已清除")


def reload_templates():
    """
    重新加载所有工具的参数模板（清除缓存后重新扫描）
    """
    clear_cache()
    return _load_templates()


def get_registered_tool_names() -> list[str]:
    """
    获取所有已注册的工具名称列表
    
    Returns:
        工具名称列表
    """
    return list(get_all_tools().keys())
