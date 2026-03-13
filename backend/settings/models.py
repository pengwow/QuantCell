import json
from typing import Any, Dict, Optional

from utils.logger import get_logger, LogType

# 获取模块日志器
logger = get_logger(__name__, LogType.APPLICATION)
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
    def set(key: str, value: str, description: str = "", plugin: str = None, name: str = None,
            is_sensitive: bool = False) -> bool:
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
            logger.info(f"配置已更新: key={key}, value={value}, plugin={plugin}, name={name}, "
                       f"is_sensitive={is_sensitive}")
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

    @staticmethod
    def get_name_with_details(name: str) -> Optional[Dict[str, Any]]:
        """获取配置项名称的详细信息
        
        Args:
            name: 配置项名称
            
        Returns:
            Optional[Dict[str, Any]]: 配置项名称的详细信息，包括键、值、描述、插件、名称、是否敏感、创建时间和更新时间
        """
        result = {}
        init_database_config()
        db: Session = SessionLocal()
        try:
            configs = db.query(SystemConfig).filter_by(name=name)
            for config in configs:
                details = SystemConfigBusiness.get_with_details(config.key)
                if details:
                    result[config.key] = details
            return result
        except Exception as e:
            logger.error(f"获取配置名称详情失败: name={name}, error={e}")
            return None
        finally:
            db.close()

    # ==================== 扁平化存储辅助方法 ====================

    @staticmethod
    def set_flattened(prefix: str, config_dict: dict, name: str = None, description: str = "") -> bool:
        """将字典配置扁平化存储，key格式为: prefix.field_name
        
        Args:
            prefix: 配置前缀，如 "exchange.binance"
            config_dict: 配置字典
            name: 配置名称，用于分组
            description: 配置描述
            
        Returns:
            bool: 是否全部保存成功
        """
        init_database_config()
        db: Session = SessionLocal()
        try:
            success_count = 0
            total_count = len(config_dict)
            
            for field_name, value in config_dict.items():
                key = f"{prefix}.{field_name}"
                
                # 确保value是字符串类型
                if isinstance(value, bool):
                    str_value = '1' if value else '0'
                elif isinstance(value, (dict, list)):
                    str_value = json.dumps(value, ensure_ascii=False)
                else:
                    str_value = str(value)
                
                # 检查配置是否已存在
                config = db.query(SystemConfig).filter_by(key=key).first()
                
                if config:
                    config.value = str_value
                    if description:
                        config.description = description
                    if name is not None:
                        config.name = name
                else:
                    config = SystemConfig(
                        key=key,
                        value=str_value,
                        description=description,
                        name=name,
                        is_sensitive=False
                    )
                    db.add(config)
                success_count += 1
            
            db.commit()
            logger.info(f"扁平化配置已保存: prefix={prefix}, fields={success_count}/{total_count}")
            return success_count == total_count
        except Exception as e:
            db.rollback()
            logger.error(f"保存扁平化配置失败: prefix={prefix}, error={e}")
            return False
        finally:
            db.close()

    @staticmethod
    def get_flattened(prefix: str) -> dict:
        """获取指定前缀的所有配置并组装为字典
        
        Args:
            prefix: 配置前缀，如 "exchange.binance"
            
        Returns:
            dict: 组装后的配置字典
        """
        init_database_config()
        db: Session = SessionLocal()
        try:
            # 查询所有以prefix开头的配置
            configs = db.query(SystemConfig).filter(SystemConfig.key.like(f"{prefix}.%")).all()
            
            result = {}
            prefix_len = len(prefix) + 1  # +1 for the dot
            
            for config in configs:
                field_name = config.key[prefix_len:]
                value = config.value
                
                # 尝试解析JSON
                try:
                    value = json.loads(value)
                except (json.JSONDecodeError, TypeError):
                    # 不是JSON，保持字符串
                    # 尝试转换为布尔值
                    if value == '1':
                        value = True
                    elif value == '0':
                        value = False
                    # 尝试转换为数字
                    elif value.isdigit():
                        value = int(value)
                    elif value.replace('.', '', 1).isdigit():
                        value = float(value)
                
                result[field_name] = value
            
            logger.info(f"扁平化配置已加载: prefix={prefix}, fields={len(result)}")
            return result
        except Exception as e:
            logger.error(f"加载扁平化配置失败: prefix={prefix}, error={e}")
            return {}
        finally:
            db.close()

    @staticmethod
    def get_all_flattened_by_prefix(base_prefix: str) -> Dict[str, dict]:
        """获取所有以base_prefix开头的配置，按子前缀分组
        
        例如: base_prefix="exchange" 会返回所有交易所配置
        {
            "binance": {"name": "币安", "trading_mode": "spot", ...},
            "okx": {"name": "OKX", "trading_mode": "spot", ...}
        }
        
        Args:
            base_prefix: 基础前缀，如 "exchange"
            
        Returns:
            Dict[str, dict]: 按子前缀分组的配置字典
        """
        init_database_config()
        db: Session = SessionLocal()
        try:
            # 查询所有以base_prefix开头的配置
            configs = db.query(SystemConfig).filter(SystemConfig.key.like(f"{base_prefix}.%")).all()
            
            result: Dict[str, dict] = {}
            base_prefix_len = len(base_prefix) + 1  # +1 for the dot
            
            for config in configs:
                # 提取子前缀 (如 "exchange.binance.name" -> "binance")
                key_without_base = config.key[base_prefix_len:]
                parts = key_without_base.split('.', 1)
                
                if len(parts) < 1:
                    continue
                    
                sub_prefix = parts[0]
                field_name = parts[1] if len(parts) > 1 else "value"
                
                if sub_prefix not in result:
                    result[sub_prefix] = {}
                
                value = config.value
                
                # 尝试解析JSON
                try:
                    value = json.loads(value)
                except (json.JSONDecodeError, TypeError):
                    # 不是JSON，尝试类型转换
                    if value == '1':
                        value = True
                    elif value == '0':
                        value = False
                    elif value.isdigit():
                        value = int(value)
                    elif value.replace('.', '', 1).isdigit():
                        value = float(value)
                
                result[sub_prefix][field_name] = value
            
            logger.info(f"扁平化配置已分组加载: base_prefix={base_prefix}, groups={len(result)}")
            return result
        except Exception as e:
            logger.error(f"加载分组扁平化配置失败: base_prefix={base_prefix}, error={e}")
            return {}
        finally:
            db.close()

    @staticmethod
    def delete_flattened(prefix: str) -> bool:
        """删除指定前缀的所有配置
        
        Args:
            prefix: 配置前缀
            
        Returns:
            bool: 是否删除成功
        """
        init_database_config()
        db: Session = SessionLocal()
        try:
            # 删除所有以prefix开头的配置
            configs = db.query(SystemConfig).filter(SystemConfig.key.like(f"{prefix}.%")).all()
            
            for config in configs:
                db.delete(config)
            
            db.commit()
            logger.info(f"扁平化配置已删除: prefix={prefix}, count={len(configs)}")
            return True
        except Exception as e:
            db.rollback()
            logger.error(f"删除扁平化配置失败: prefix={prefix}, error={e}")
            return False
        finally:
            db.close()