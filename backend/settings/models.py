import json
from typing import Any, Dict, Optional

from utils.logger import get_logger, LogType

logger = get_logger(__name__, LogType.APPLICATION)
from sqlalchemy.orm import Session

from collector.db.database import SessionLocal, init_database_config
from collector.db.models import SystemConfig


def _parse_config_value(value: str):
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

    @staticmethod
    def get(key: str, default: Any = None) -> Any:
        init_database_config()
        db: Session = SessionLocal()
        try:
            config = db.query(SystemConfig).filter_by(key=key).first()
            return config.value if config else default
        except Exception as e:
            logger.error(f"获取配置失败: key={key}, error={e}")
            return default
        finally:
            db.close()

    @staticmethod
    def set(key: str, value: str, description: str = "", plugin: Optional[str] = None, name: Optional[str] = None,
            is_sensitive: bool = False) -> bool:
        init_database_config()
        db: Session = SessionLocal()
        try:
            config = db.query(SystemConfig).filter_by(key=key).first()

            if isinstance(value, bool):
                str_value = '1' if value else '0'
            else:
                str_value = str(value)

            if config:
                config.value = str_value
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
        init_database_config()
        db: Session = SessionLocal()
        try:
            configs = db.query(SystemConfig).all()
            result = {config.key: config.value for config in configs}
            return result
        except Exception as e:
            logger.error(f"获取所有配置失败: error={e}")
            return {}
        finally:
            db.close()

    @staticmethod
    def get_all_with_details() -> Dict[str, Dict[str, Any]]:
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

            configs = db.query(SystemConfig).all()
            result = {}
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
        import pytz
        init_database_config()
        db: Session = SessionLocal()
        try:
            config = db.query(SystemConfig).filter_by(key=key).first()
            if config:
                def format_datetime(dt):
                    if dt is None:
                        return None
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=pytz.utc)
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

    @staticmethod
    def set_flattened(prefix: str, config_dict: dict, name: Optional[str] = None, description: str = "") -> bool:
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
        init_database_config()
        db: Session = SessionLocal()
        try:
            configs = db.query(SystemConfig).filter(
                SystemConfig.key.like(f"{prefix}.%")
            ).all()

            result = {}
            prefix_len = len(prefix) + 1

            for config in configs:
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
    def get_all_flattened_by_prefix(base_prefix: str) -> Dict[str, dict]:
        init_database_config()
        db: Session = SessionLocal()
        try:
            base_prefix_len = len(base_prefix) + 1

            configs = db.query(SystemConfig).filter(
                SystemConfig.key.like(f"{base_prefix}.%")
            ).all()

            result: Dict[str, dict] = {}
            for config in configs:
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
    def delete_flattened(prefix: str) -> bool:
        init_database_config()
        db: Session = SessionLocal()
        try:
            configs = db.query(SystemConfig).filter(
                SystemConfig.key.like(f"{prefix}.%")
            ).all()

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
