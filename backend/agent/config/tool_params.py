"""
工具参数解析器

提供统一的参数读取逻辑，支持多级优先级：
1. 数据库配置 (SystemConfig 表)
2. 环境变量 (os.environ)
3. 参数模板默认值

使用示例:
    from agent.config.tool_params import ToolParamResolver
    
    # 解析单个参数
    api_key = ToolParamResolver.resolve("web_search", "api_key")
    
    # 解析所有参数
    params = ToolParamResolver.resolve_all("web_search")
    
    # 验证参数值
    is_valid, error = ToolParamResolver.validate("web_search", "max_results", 15)
"""

import os
from typing import Any, Optional, Tuple
from utils.logger import get_logger, LogType

logger = get_logger(__name__, LogType.APPLICATION)


class ToolParamResolver:
    """
    工具参数解析器
    
    解析优先级（从高到低）：
    1. 数据库配置 (SystemConfig 表)
    2. 环境变量 (os.environ) - 通过 param_template 的 env_key 字段映射
    3. 参数模板默认值
    """

    PREFIX = "agent.tools"

    @classmethod
    def resolve(cls, tool_name: str, param_name: str) -> Any:
        """
        解析单个参数值
        
        Args:
            tool_name: 工具名称 (如 "web_search")
            param_name: 参数名称 (如 "api_key")
            
        Returns:
            参数值，如果都未配置则返回默认值（可能为None）
        """
        # 延迟导入避免循环依赖
        from agent.config.templates import get_tool_template
        
        # 1. 获取参数模板
        template = get_tool_template(tool_name, param_name)
        if not template:
            logger.warning(f"未知参数: {tool_name}.{param_name}")
            return None
        
        target_type = template.get("type", "string")
        
        # 2. 构建数据库键名并尝试从数据库读取
        db_key = f"{cls.PREFIX}.{tool_name}.{param_name}"
        
        try:
            from settings.models import SystemConfigBusiness
            db_value = SystemConfigBusiness.get(db_key)
            
            if db_value is not None:
                logger.debug(f"参数 {db_key} 从数据库获取")
                return cls._convert_type(db_value, target_type)
                
        except Exception as e:
            logger.error(f"读取数据库配置失败 {db_key}: {e}")
        
        # 3. 尝试从环境变量读取
        env_key = template.get("env_key")
        if env_key:
            env_value = os.environ.get(env_key)
            if env_value is not None:
                logger.debug(f"参数 {db_key} 从环境变量 {env_key} 获取")
                return cls._convert_type(env_value, target_type)
        
        # 4. 返回默认值
        default = template.get("default")
        logger.debug(f"参数 {db_key} 使用默认值: {default}")
        return default

    @classmethod
    def resolve_all(cls, tool_name: str) -> dict:
        """
        解析工具的所有参数
        
        Args:
            tool_name: 工具名称
            
        Returns:
            {param_name: value} 字典
        """
        from agent.config.templates import get_tool_template
        
        template = get_tool_template(tool_name)
        if not template:
            return {}
        
        result = {}
        for param_name in template.keys():
            result[param_name] = cls.resolve(tool_name, param_name)
        
        return result

    @classmethod
    def get_param_source(cls, tool_name: str, param_name: str) -> str:
        """
        获取参数值的实际来源
        
        Args:
            tool_name: 工具名称
            param_name: 参数名称
            
        Returns:
            来源字符串: "database" | "environment" | "default" | "unknown"
        """
        from agent.config.templates import get_tool_template
        
        template = get_tool_template(tool_name, param_name)
        if not template:
            return "unknown"
        
        db_key = f"{cls.PREFIX}.{tool_name}.{param_name}"
        
        try:
            from settings.models import SystemConfigBusiness
            db_value = SystemConfigBusiness.get(db_key)
            
            if db_value is not None:
                return "database"
                
        except Exception:
            pass
        
        env_key = template.get("env_key")
        if env_key and os.environ.get(env_key):
            return "environment"
        
        return "default"

    @classmethod
    def _convert_type(cls, value: Any, target_type: str) -> Any:
        """
        类型转换
        
        Args:
            value: 要转换的值（通常是字符串）
            target_type: 目标类型
            
        Returns:
            转换后的值
        """
        if value is None:
            return None
            
        if target_type == "integer":
            try:
                return int(value)
            except (ValueError, TypeError):
                logger.warning(f"无法将 {value} 转换为 integer")
                return value
                
        elif target_type == "float":
            try:
                return float(value)
            except (ValueError, TypeError):
                logger.warning(f"无法将 {value} 转换为 float")
                return value
                
        elif target_type == "boolean":
            if isinstance(value, bool):
                return value
            if isinstance(value, str):
                return value.lower() in ("true", "1", "yes", "on")
            return bool(value)
            
        else:  # string 或其他类型
            return str(value)

    @classmethod
    def validate(
        cls, 
        tool_name: str, 
        param_name: str, 
        value: Any
    ) -> Tuple[bool, str]:
        """
        验证参数值是否符合模板定义
        
        Args:
            tool_name: 工具名称
            param_name: 参数名称
            value: 要验证的值
            
        Returns:
            (is_valid, error_message) 元组
        """
        from agent.config.templates import get_tool_template
        
        template = get_tool_template(tool_name, param_name)
        if not template:
            return False, f"未知参数: {param_name}"
        
        target_type = template.get("type", "string")
        
        # 类型检查
        if value is not None and target_type != "string":
            try:
                if target_type == "integer":
                    int(value)
                elif target_type == "float":
                    float(value)
                elif target_type == "boolean":
                    if isinstance(value, str):
                        value.lower() in ("true", "1", "yes", "on")
            except (ValueError, TypeError):
                return False, f"类型错误: 期望 {target_type}, 得到 {type(value).__name__}"
        
        # 范围检查
        validation = template.get("validation")
        if validation and value is not None:
            try:
                num_value = float(value) if target_type in ("float", "integer") else None
                
                if num_value is not None:
                    min_val = validation.get("min")
                    max_val = validation.get("max")
                    
                    if min_val is not None and num_value < min_val:
                        return False, f"值 {value} 小于最小值 {min_val}"
                    
                    if max_val is not None and num_value > max_val:
                        return False, f"值 {value} 大于最大值 {max_val}"
                        
            except (ValueError, TypeError):
                pass
        
        # 必填检查
        required = template.get("required", False)
        if required and (value is None or value == ""):
            return False, f"参数 {param_name} 为必填项"
        
        return True, ""
