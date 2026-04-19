"""
工具参数管理器

提供完整的CRUD操作和高级管理功能：
- 参数的增删改查
- 批量导入/导出
- 参数验证
- 敏感信息保护

使用示例:
    from agent.config.manager import ToolParamManager
    
    # 获取工具参数（敏感值自动脱敏）
    params = ToolParamManager.get_tool_params("web_search")
    
    # 设置参数
    ToolParamManager.set_tool_param("web_search", "api_key", "your-key")
    
    # 批量更新
    result = ToolParamManager.batch_update("web_search", {"max_results": 10})
    
    # 导出配置
    config = ToolParamManager.export_config()
"""

import os
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from utils.logger import get_logger, LogType

logger = get_logger(__name__, LogType.APPLICATION)


def _get_db_session():
    """
    获取数据库会话（延迟导入避免循环依赖）
    
    Returns:
        (db, SessionLocal) 元组或 (None, None) 如果失败
    """
    try:
        from collector.db.database import SessionLocal, init_database_config
        from collector.db.models import SystemConfig
        
        init_database_config()
        db = SessionLocal()
        return db, SystemConfig
    except Exception as e:
        logger.error(f"获取数据库会话失败: {e}")
        return None, None


def _db_get(key: str) -> Optional[str]:
    """从数据库读取配置值"""
    db, SystemConfig = _get_db_session()
    if not db:
        return None
    
    try:
        config = db.query(SystemConfig).filter_by(key=key).first()
        return config.value if config else None
    except Exception as e:
        logger.error(f"读取配置失败 {key}: {e}")
        return None
    finally:
        try:
            db.close()
        except:
            pass


def _db_set(key: str, value: str, description: str = "", plugin: str = None,
            name: str = None, is_sensitive: bool = False) -> bool:
    """向数据库写入配置值"""
    db, SystemConfig = _get_db_session()
    if not db:
        return False
    
    try:
        config = db.query(SystemConfig).filter_by(key=key).first()
        
        if config:
            config.value = value
            if description:
                config.description = description
            if plugin is not None:
                config.plugin = plugin
            if name is not None:
                config.name = name
            config.is_sensitive = is_sensitive
        else:
            config = SystemConfig(
                key=key,
                value=value,
                description=description,
                plugin=plugin,
                name=name,
                is_sensitive=is_sensitive
            )
            db.add(config)
        
        db.commit()
        return True
    except Exception as e:
        db.rollback()
        logger.error(f"写入配置失败 {key}: {e}")
        return False
    finally:
        try:
            db.close()
        except:
            pass


def _db_delete(key: str) -> bool:
    """从数据库删除配置"""
    db, SystemConfig = _get_db_session()
    if not db:
        return False
    
    try:
        config = db.query(SystemConfig).filter_by(key=key).first()
        if config:
            db.delete(config)
            db.commit()
        return True
    except Exception as e:
        db.rollback()
        logger.error(f"删除配置失败 {key}: {e}")
        return False
    finally:
        try:
            db.close()
        except:
            pass


def mask_sensitive_value(value: Optional[str], show_chars: int = 4) -> str:
    """
    脱敏处理
    
    Args:
        value: 原始值
        show_chars: 显示的字符数
        
    Returns:
        脱敏后的字符串
    """
    if not value:
        return "未配置"
    
    value_str = str(value)
    if len(value_str) <= show_chars:
        return "*" * len(value_str)
    
    return value_str[:show_chars] + "*" * (len(value_str) - show_chars)


class ToolParamManager:
    """
    工具参数管理器
    
    提供：
    - 参数的增删改查
    - 批量导入/导出
    - 参数验证
    - 敏感信息保护
    """

    PREFIX = "agent.tools"

    @staticmethod
    def get_tool_params(
        tool_name: str, 
        include_sensitive: bool = False
    ) -> Dict[str, Dict[str, Any]]:
        """
        获取工具的所有参数
        
        Args:
            tool_name: 工具名称
            include_sensitive: 是否包含敏感参数的真实值
            
        Returns:
            {param_name: {value, configured, source, sensitive, type, description}}
            
        Raises:
            ValueError: 如果工具不存在
        """
        from agent.config.templates import get_tool_template
        
        template = get_tool_template(tool_name)
        
        # 区分：None 表示工具不存在，{} 表示工具存在但无参数
        if template is None:
            raise ValueError(f"未知工具: {tool_name}")
        
        # 工具存在但无参数模板，返回空字典
        if not template:
            return {}
        
        result: Dict[str, Dict[str, Any]] = {}
        
        for param_name, meta in template.items():
            db_key = f"{ToolParamManager.PREFIX}.{tool_name}.{param_name}"
            
            db_value = _db_get(db_key)
            
            if db_value is not None:
                source = "database"
                value = db_value
            elif meta.get("env_key") and os.environ.get(meta["env_key"]):
                source = "environment"
                value = os.environ[meta["env_key"]]
            else:
                source = "default"
                value = meta.get("default")
            
            if meta.get("sensitive") and not include_sensitive and source != "default":
                display_value = mask_sensitive_value(value)
            else:
                display_value = value
            
            result[param_name] = {
                "value": display_value,
                "configured": db_value is not None,
                "source": source,
                "sensitive": meta.get("sensitive", False),
                "type": meta.get("type"),
                "description": meta.get("description", "")
            }
        
        return result

    @staticmethod
    def set_tool_param(
        tool_name: str, 
        param_name: str, 
        value: Any
    ) -> bool:
        """
        设置工具参数
        
        Args:
            tool_name: 工具名称
            param_name: 参数名称
            value: 参数值
            
        Returns:
            是否设置成功
            
        Raises:
            ValueError: 如果参数不存在或值无效
        """
        from agent.config.templates import get_tool_template
        from agent.config.tool_params import ToolParamResolver
        
        template = get_tool_template(tool_name, param_name)
        if not template:
            raise ValueError(f"未知参数: {tool_name}.{param_name}")
        
        is_valid, error_msg = ToolParamResolver.validate(
            tool_name, param_name, value
        )
        if not is_valid:
            raise ValueError(error_msg)
        
        db_key = f"{ToolParamManager.PREFIX}.{tool_name}.{param_name}"
        
        success = _db_set(
            key=db_key,
            value=str(value),
            description=template.get("description", ""),
            plugin="agent",
            name=tool_name,
            is_sensitive=template.get("sensitive", False)
        )
        
        if success:
            logger.info(f"工具参数已更新: {db_key}")
        
        return success

    @staticmethod
    def delete_tool_param(tool_name: str, param_name: str) -> bool:
        """
        删除工具参数（恢复使用环境变量或默认值）
        
        Args:
            tool_name: 工具名称
            param_name: 参数名称
            
        Returns:
            是否删除成功
        """
        db_key = f"{ToolParamManager.PREFIX}.{tool_name}.{param_name}"
        success = _db_delete(db_key)
        
        if success:
            logger.info(f"工具参数已删除: {db_key}")
        
        return success

    @staticmethod
    def batch_update(
        tool_name: str,
        params: Dict[str, Any],
        overwrite: bool = False
    ) -> Dict[str, List[str]]:
        """
        批量更新参数
        
        Args:
            tool_name: 工具名称
            params: {param_name: value}
            overwrite: 是否覆盖已有值
            
        Returns:
            {"updated": [...], "skipped": [...], "errors": [...]}
        """
        result: Dict[str, List[str]] = {
            "updated": [],
            "skipped": [],
            "errors": []
        }
        
        for param_name, value in params.items():
            try:
                db_key = f"{ToolParamManager.PREFIX}.{tool_name}.{param_name}"
                
                existing = _db_get(db_key)
                
                if existing and not overwrite:
                    result["skipped"].append(param_name)
                    continue
                
                if ToolParamManager.set_tool_param(tool_name, param_name, value):
                    result["updated"].append(param_name)
                else:
                    result["errors"].append(f"{param_name}: 保存失败")
                    
            except ValueError as e:
                result["errors"].append(f"{param_name}: {str(e)}")
            except Exception as e:
                result["errors"].append(f"{param_name}: {str(e)}")
        
        return result

    @staticmethod
    def get_registered_tools() -> List[Dict[str, Any]]:
        """
        获取所有已注册工具的信息
        
        Returns:
            工具信息列表，每个元素包含 name, param_count, configured_count 等
        """
        from agent.config.templates import get_all_tools
        
        templates = get_all_tools()
        result: List[Dict[str, Any]] = []
        
        db, SystemConfig = _get_db_session()
        
        if not db:
            return result
        
        try:
            for tool_name, template in templates.items():
                configured_count = 0
                total_params = len(template)
                
                for param_name in template.keys():
                    db_key = f"{ToolParamManager.PREFIX}.{tool_name}.{param_name}"
                    try:
                        config = db.query(SystemConfig).filter_by(key=db_key).first()
                        if config is not None:
                            configured_count += 1
                    except Exception:
                        pass
                
                has_required = True
                for pn, meta in template.items():
                    if meta.get("required"):
                        db_key = f"{ToolParamManager.PREFIX}.{tool_name}.{pn}"
                        has_db = False
                        has_env = False
                        
                        try:
                            config = db.query(SystemConfig).filter_by(key=db_key).first()
                            has_db = config is not None
                        except Exception:
                            pass
                        
                        env_key = meta.get("env_key")
                        if env_key:
                            has_env = env_key in os.environ
                        
                        if not has_db and not has_env:
                            has_required = False
                            break
                
                result.append({
                    "name": tool_name,
                    "param_count": total_params,
                    "configured_count": configured_count,
                    "has_required_params": has_required
                })
                
        except Exception as e:
            logger.error(f"获取已注册工具列表失败: {e}")
        finally:
            try:
                db.close()
            except:
                pass
        
        return result

    @staticmethod
    def export_config(tool_name: Optional[str] = None) -> Dict[str, Any]:
        """
        导出配置（敏感值始终脱敏）
        
        Args:
            tool_name: 工具名称，None表示导出所有工具
            
        Returns:
            导出的配置字典
        """
        export_data: Dict[str, Any] = {
            "export_time": datetime.now().isoformat(),
            "version": "1.0",
            "tools": {}
        }
        
        from agent.config.templates import get_all_tools
        
        tools_to_export = [tool_name] if tool_name else list(get_all_tools().keys())
        
        for tname in tools_to_export:
            try:
                params = ToolParamManager.get_tool_params(
                    tname, 
                    include_sensitive=False
                )
                
                export_data["tools"][tname] = {
                    pname: pinfo["value"] 
                    for pname, pinfo in params.items()
                }
            except ValueError as e:
                logger.warning(f"导出配置跳过未知工具: {tname} - {e}")
        
        return export_data

    @staticmethod
    def import_config(
        config: Dict[str, Any], 
        overwrite: bool = False
    ) -> Tuple[int, int, List[str]]:
        """
        导入配置
        
        Args:
            config: 导入的配置字典
            overwrite: 是否覆盖已有值
            
        Returns:
            (imported_count, skipped_count, errors)
        """
        imported = 0
        skipped = 0
        errors: List[str] = []
        
        tools_config = config.get("tools", {})
        
        for tool_name, params in tools_config.items():
            from agent.config.templates import get_tool_template
            
            if not get_tool_template(tool_name):
                errors.append(f"未知工具: {tool_name}")
                continue
            
            if not isinstance(params, dict):
                errors.append(f"工具 {tool_name} 的参数格式错误")
                continue
            
            result = ToolParamManager.batch_update(
                tool_name, params, overwrite
            )
            
            imported += len(result["updated"])
            skipped += len(result["skipped"])
            errors.extend(result["errors"])
        
        return imported, skipped, errors


class ToolParamValidator:
    """参数验证器（内部使用）"""
    
    @staticmethod
    def validate(
        tool_name: str, 
        param_name: str, 
        value: Any
    ) -> Tuple[bool, str]:
        """
        验证参数值
        
        委托给 ToolParamResolver.validate()
        """
        from agent.config.tool_params import ToolParamResolver
        
        return ToolParamResolver.validate(tool_name, param_name, value)
