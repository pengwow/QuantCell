import json
from typing import Any, Dict, Optional

from utils.logger import get_logger, LogType

# 获取模块日志器
logger = get_logger(__name__, LogType.APPLICATION)
from sqlalchemy.orm import Session

# 导入数据库连接和SystemConfig模型
from collector.db.database import SessionLocal, init_database_config
from collector.db.models import SystemConfig


def _parse_config_value(value: str):
    """解析配置值，尝试转换为合适的Python类型

    Args:
        value: 字符串类型的配置值

    Returns:
        解析后的值（可能是bool、int、float或原始字符串）
    """
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        if value == '1':
            return True
        elif value == '0':
            return False
        elif value.isdigit():
            return int(value)
        elif value.replace('.', '', 1).isdigit():
            return float(value)
        return value


class SystemConfigBusiness:
    """系统配置模型类

    用于操作system_config表，提供CRUD操作方法
    兼容SQLite和DuckDB
    """
    
    @staticmethod
    def get(key: str, default: Any = None, user_id: Optional[int] = None) -> Any:
        """获取配置项的值，优先返回用户专属配置，否则回退到系统级配置

        Args:
            key: 配置项键名
            default: 默认值，如果配置项不存在则返回默认值
            user_id: 用户ID，用于用户隔离

        Returns:
            Any: 配置项的值或默认值
        """
        init_database_config()
        db: Session = SessionLocal()
        try:
            if user_id is not None:
                # 优先查找用户专属配置
                config = db.query(SystemConfig).filter_by(key=key, user_id=user_id).first()
                if config:
                    return config.value
            # 回退到系统级配置（user_id为NULL）
            config = db.query(SystemConfig).filter_by(key=key, user_id=None).first()
            return config.value if config else default
        except Exception as e:
            logger.error(f"获取配置失败: key={key}, error={e}")
            return default
        finally:
            db.close()
    
    @staticmethod
    def set(key: str, value: str, description: str = "", plugin: Optional[str] = None, name: Optional[str] = None,
            is_sensitive: bool = False, user_id: Optional[int] = None) -> bool:
        """设置配置项的值

        Args:
            key: 配置项键名
            value: 配置项值
            description: 配置项描述
            plugin: 插件名称，用于区分是插件配置还是基础配置
            name: 配置名称，用于区分系统配置页面的子菜单名称
            is_sensitive: 是否为敏感配置，敏感配置API不返回真实值
            user_id: 用户ID，用于用户隔离

        Returns:
            bool: 设置成功返回True，失败返回False
        """
        init_database_config()
        db: Session = SessionLocal()
        try:
            query = db.query(SystemConfig).filter_by(key=key)
            if user_id is not None:
                query = query.filter_by(user_id=user_id)
            config = query.first()

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
                    is_sensitive=is_sensitive,
                    user_id=user_id
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
    def delete(key: str, user_id: Optional[int] = None) -> bool:
        """删除配置项

        Args:
            key: 配置项键名
            user_id: 用户ID，用于用户隔离

        Returns:
            bool: 删除成功返回True，失败返回False
        """
        init_database_config()
        db: Session = SessionLocal()
        try:
            query = db.query(SystemConfig).filter_by(key=key)
            if user_id is not None:
                query = query.filter_by(user_id=user_id)
            config = query.first()
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
    def get_all(user_id: Optional[int] = None) -> Dict[str, str]:
        """获取所有配置项，用户配置覆盖系统级配置

        Args:
            user_id: 用户ID，用于用户隔离

        Returns:
            Dict[str, str]: 合并后的配置项，用户专属配置优先
        """
        init_database_config()
        db: Session = SessionLocal()
        try:
            # 先加载系统级配置作为基础
            system_configs = db.query(SystemConfig).filter(SystemConfig.user_id.is_(None)).all()
            result = {config.key: config.value for config in system_configs}

            if user_id is not None:
                # 用户专属配置覆盖系统级配置
                user_configs = db.query(SystemConfig).filter_by(user_id=user_id).all()
                for config in user_configs:
                    result[config.key] = config.value

            return result
        except Exception as e:
            logger.error(f"获取所有配置失败: error={e}")
            return {}
        finally:
            db.close()
    
    @staticmethod
    def get_all_with_details(user_id: Optional[int] = None) -> Dict[str, Dict[str, Any]]:
        """获取所有配置项的详细信息，用户配置覆盖系统级配置

        Args:
            user_id: 用户ID，用于用户隔离

        Returns:
            Dict[str, Dict[str, Any]]: 合并后的配置详情，用户专属配置优先
        """
        import pytz
        init_database_config()
        db: Session = SessionLocal()
        try:
            def format_datetime(dt):
                if dt is None:
                    return None
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=pytz.utc)
                return dt.astimezone(pytz.timezone('Asia/Shanghai')).strftime('%Y-%m-%d %H:%M:%S')

            # 先加载系统级配置作为基础
            system_configs = db.query(SystemConfig).filter(SystemConfig.user_id.is_(None)).all()
            result = {}
            for config in system_configs:
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

            if user_id is not None:
                # 用户专属配置覆盖系统级配置
                user_configs = db.query(SystemConfig).filter_by(user_id=user_id).all()
                for config in user_configs:
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
    def get_with_details(key: str, user_id: Optional[int] = None) -> Optional[Dict[str, Any]]:
        """获取配置项的详细信息

        Args:
            key: 配置项键名
            user_id: 用户ID，用于用户隔离

        Returns:
            Optional[Dict[str, Any]]: 配置的详细信息，包括键、值、描述、插件、名称、是否敏感、创建时间和更新时间
        """
        import pytz
        init_database_config()
        db: Session = SessionLocal()
        try:
            query = db.query(SystemConfig).filter_by(key=key)
            if user_id is not None:
                query = query.filter_by(user_id=user_id)
            config = query.first()
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
    def set_flattened(prefix: str, config_dict: dict, name: Optional[str] = None, description: str = "",
                      user_id: Optional[int] = None) -> bool:
        """将字典配置扁平化存储，key格式为: prefix.field_name

        Args:
            prefix: 配置前缀，如 "exchange.binance"
            config_dict: 配置字典
            name: 配置名称，用于分组
            description: 配置描述
            user_id: 用户ID，用于用户隔离

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

                if isinstance(value, bool):
                    str_value = '1' if value else '0'
                elif isinstance(value, (dict, list)):
                    str_value = json.dumps(value, ensure_ascii=False)
                else:
                    str_value = str(value)

                query = db.query(SystemConfig).filter_by(key=key)
                if user_id is not None:
                    query = query.filter_by(user_id=user_id)
                config = query.first()

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
                        is_sensitive=False,
                        user_id=user_id
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
    def get_flattened(prefix: str, user_id: Optional[int] = None) -> dict:
        """获取指定前缀的所有配置并组装为字典，用户配置覆盖系统级配置

        Args:
            prefix: 配置前缀，如 "exchange.binance"
            user_id: 用户ID，用于用户隔离

        Returns:
            dict: 组装后的配置字典
        """
        init_database_config()
        db: Session = SessionLocal()
        try:
            # 加载系统级配置作为基础
            system_configs = db.query(SystemConfig).filter(
                SystemConfig.key.like(f"{prefix}.%"),
                SystemConfig.user_id.is_(None)
            ).all()

            result = {}
            prefix_len = len(prefix) + 1

            for config in system_configs:
                field_name = config.key[prefix_len:]
                result[field_name] = _parse_config_value(config.value)

            if user_id is not None:
                # 用户专属配置覆盖
                user_configs = db.query(SystemConfig).filter(
                    SystemConfig.key.like(f"{prefix}.%"),
                    SystemConfig.user_id == user_id
                ).all()
                for config in user_configs:
                    field_name = config.key[prefix_len:]
                    result[field_name] = _parse_config_value(config.value)

            logger.info(f"扁平化配置已加载: prefix={prefix}, fields={len(result)}")
            return result
        except Exception as e:
            logger.error(f"加载扁平化配置失败: prefix={prefix}, error={e}")
            return {}
        finally:
            db.close()

    @staticmethod
    def get_all_flattened_by_prefix(base_prefix: str, user_id: Optional[int] = None) -> Dict[str, dict]:
        """获取所有以base_prefix开头的配置，按子前缀分组，用户配置覆盖系统级配置

        Args:
            base_prefix: 基础前缀，如 "exchange"
            user_id: 用户ID，用于用户隔离

        Returns:
            Dict[str, dict]: 按子前缀分组的配置字典
        """
        init_database_config()
        db: Session = SessionLocal()
        try:
            base_prefix_len = len(base_prefix) + 1

            # 加载系统级配置作为基础
            system_configs = db.query(SystemConfig).filter(
                SystemConfig.key.like(f"{base_prefix}.%"),
                SystemConfig.user_id.is_(None)
            ).all()

            result: Dict[str, dict] = {}
            for config in system_configs:
                key_without_base = config.key[base_prefix_len:]
                parts = key_without_base.split('.', 1)
                if len(parts) < 1:
                    continue
                sub_prefix = parts[0]
                field_name = parts[1] if len(parts) > 1 else "value"
                if sub_prefix not in result:
                    result[sub_prefix] = {}
                result[sub_prefix][field_name] = _parse_config_value(config.value)

            if user_id is not None:
                # 用户专属配置覆盖
                user_configs = db.query(SystemConfig).filter(
                    SystemConfig.key.like(f"{base_prefix}.%"),
                    SystemConfig.user_id == user_id
                ).all()
                for config in user_configs:
                    key_without_base = config.key[base_prefix_len:]
                    parts = key_without_base.split('.', 1)
                    if len(parts) < 1:
                        continue
                    sub_prefix = parts[0]
                    field_name = parts[1] if len(parts) > 1 else "value"
                    if sub_prefix not in result:
                        result[sub_prefix] = {}
                    result[sub_prefix][field_name] = _parse_config_value(config.value)

            logger.info(f"扁平化配置已分组加载: base_prefix={base_prefix}, groups={len(result)}")
            return result
        except Exception as e:
            logger.error(f"加载分组扁平化配置失败: base_prefix={base_prefix}, error={e}")
            return {}
        finally:
            db.close()

    @staticmethod
    def delete_flattened(prefix: str, user_id: Optional[int] = None) -> bool:
        """删除指定前缀的所有配置

        Args:
            prefix: 配置前缀
            user_id: 用户ID，为None时删除系统级配置

        Returns:
            bool: 是否删除成功
        """
        init_database_config()
        db: Session = SessionLocal()
        try:
            query = db.query(SystemConfig).filter(SystemConfig.key.like(f"{prefix}.%"))
            if user_id is not None:
                query = query.filter_by(user_id=user_id)
            else:
                query = query.filter(SystemConfig.user_id.is_(None))
            configs = query.all()

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