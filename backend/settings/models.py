import json
from typing import Any, Dict, Optional

from loguru import logger
from sqlalchemy.orm import Session

# 导入数据库连接和SystemConfig模型
from collector.db.database import SessionLocal, init_database_config
from collector.db.models import SystemConfig


class SystemConfigBusiness:
    """系统配置模型类
    
    用于操作system_config表，提供CRUD操作方法
    兼容SQLite和DuckDB
    """
    
    @staticmethod
    def get(key: str, default: Any = None) -> Any:
        """获取配置项的值
        
        Args:
            key: 配置项键名
            default: 默认值，如果配置项不存在则返回默认值
            
        Returns:
            Any: 配置项的值或默认值
        """
        init_database_config()
        db: Session = SessionLocal()
        try:
            config = db.query(SystemConfig).filter_by(key=key).first()
            if config:
                return config.value
            return default
        except Exception as e:
            logger.error(f"获取配置失败: key={key}, error={e}")
            return default
        finally:
            db.close()
    
    @staticmethod
    def set(key: str, value: str, description: str = "", plugin: str = None, name: str = None, is_sensitive: bool = False) -> bool:
        """设置配置项的值
        
        Args:
            key: 配置项键名
            value: 配置项值
            description: 配置项描述
            plugin: 插件名称，用于区分是插件配置还是基础配置
            name: 配置名称，用于区分系统配置页面的子菜单名称
            is_sensitive: 是否为敏感配置，敏感配置API不返回真实值
            
        Returns:
            bool: 设置成功返回True，失败返回False
        """
        init_database_config()
        db: Session = SessionLocal()
        try:
            # 检查配置是否已存在
            config = db.query(SystemConfig).filter_by(key=key).first()
            
            # 确保value是字符串类型，因为数据库字段是String类型
            if isinstance(value, bool):
                # 布尔值转换为字符串
                str_value = '1' if value else '0'
            else:
                # 其他类型转换为字符串
                str_value = str(value)
            
            if config:
                # 更新现有配置
                config.value = str_value
                if description:
                    config.description = description
                if plugin is not None:
                    config.plugin = plugin
                if name is not None:
                    config.name = name
                config.is_sensitive = is_sensitive
            else:
                # 创建新配置
                config = SystemConfig(
                    key=key,
                    value=str_value,
                    description=description,
                    plugin=plugin,
                    name=name,
                    is_sensitive=is_sensitive
                )
                db.add(config)
            db.commit()
            logger.info(f"配置已更新: key={key}, value={value}, plugin={plugin}, name={name}, is_sensitive={is_sensitive}")
            return True
        except Exception as e:
            db.rollback()
            logger.error(f"更新配置失败: key={key}, error={e}")
            return False
        finally:
            db.close()
    
    @staticmethod
    def delete(key: str) -> bool:
        """删除配置项
        
        Args:
            key: 配置项键名
            
        Returns:
            bool: 删除成功返回True，失败返回False
        """
        init_database_config()
        db: Session = SessionLocal()
        try:
            config = db.query(SystemConfig).filter_by(key=key).first()
            if config:
                db.delete(config)
                db.commit()
                logger.info(f"配置已删除: key={key}")
            return True
        except Exception as e:
            db.rollback()
            logger.error(f"删除配置失败: key={key}, error={e}")
            return False
        finally:
            db.close()
    
    @staticmethod
    def get_all() -> Dict[str, str]:
        """获取所有配置项
        
        Returns:
            Dict[str, str]: 所有配置项，键为配置项键名，值为配置项值
        """
        init_database_config()
        db: Session = SessionLocal()
        try:
            configs = db.query(SystemConfig).all()
            return {config.key: config.value for config in configs}  # pyright: ignore[reportReturnType]
        except Exception as e:
            logger.error(f"获取所有配置失败: error={e}")
            return {}
        finally:
            db.close()
    
    @staticmethod
    def get_all_with_details() -> Dict[str, Dict[str, Any]]:
        """获取所有配置项的详细信息
        
        Returns:
            Dict[str, Dict[str, Any]]: 所有配置项的详细信息，键为配置项键名
        """
        import pytz
        init_database_config()
        db: Session = SessionLocal()
        try:
            configs = db.query(SystemConfig).all()
            result = {}
            
            def format_datetime(dt):
                if dt is None:
                    return None
                # 如果datetime对象没有时区信息，添加UTC时区
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=pytz.utc)
                # 转换为UTC+8时间并格式化为字符串
                return dt.astimezone(pytz.timezone('Asia/Shanghai')).strftime('%Y-%m-%d %H:%M:%S')
            
            for config in configs:
                result[config.key] = {
                    "key": config.key,
                    "value": config.value,
                    "description": config.description,
                    "plugin": config.plugin,
                    "name": config.name,
                    "is_sensitive": config.is_sensitive,
                    "created_at": format_datetime(config.created_at),
                    "updated_at": format_datetime(config.updated_at)
                }
            return result
        except Exception as e:
            logger.error(f"获取所有配置详情失败: error={e}")
            return {}
        finally:
            db.close()
    
    @staticmethod
    def get_with_details(key: str) -> Optional[Dict[str, Any]]:
        """获取配置项的详细信息
        
        Args:
            key: 配置项键名
            
        Returns:
            Optional[Dict[str, Any]]: 配置的详细信息，包括键、值、描述、插件、名称、是否敏感、创建时间和更新时间
        """
        import pytz
        init_database_config()
        db: Session = SessionLocal()
        try:
            config = db.query(SystemConfig).filter_by(key=key).first()
            if config:
                def format_datetime(dt):
                    if dt is None:
                        return None
                    # 如果datetime对象没有时区信息，添加UTC时区
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=pytz.utc)
                    # 转换为UTC+8时间并格式化为字符串
                    return dt.astimezone(pytz.timezone('Asia/Shanghai')).strftime('%Y-%m-%d %H:%M:%S')
                
                return {
                    "key": config.key,
                    "value": config.value,
                    "description": config.description,
                    "plugin": config.plugin,
                    "name": config.name,
                    "is_sensitive": config.is_sensitive,
                    "created_at": format_datetime(config.created_at),
                    "updated_at": format_datetime(config.updated_at)
                }
            return None
        except Exception as e:
            logger.error(f"获取配置详情失败: key={key}, error={e}")
            return None
        finally:
            db.close()