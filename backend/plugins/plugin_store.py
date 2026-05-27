import json
from typing import Any, Dict, List, Optional

import pytz
from sqlalchemy.orm import Session

from collector.db.database import SessionLocal, init_database_config
from collector.db.models import Plugin
from utils.logger import get_logger, LogType

logger = get_logger(__name__, LogType.APPLICATION)


def _format_datetime(dt):
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=pytz.utc)
    return dt.astimezone(pytz.timezone('Asia/Shanghai')).strftime('%Y-%m-%d %H:%M:%S')


def _serialize_json_field(value):
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return value


def _deserialize_json_field(value):
    if value is None:
        return None
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return value


class PluginStore:

    @staticmethod
    def save_plugin(metadata: dict) -> bool:
        init_database_config()
        db: Session = SessionLocal()
        try:
            name = metadata.get('name')
            if not name:
                logger.error("保存插件失败: 缺少 name 字段")
                return False

            plugin = db.query(Plugin).filter_by(name=name).first()

            permissions = _serialize_json_field(metadata.get('permissions'))
            config_schema = _serialize_json_field(metadata.get('config_schema'))

            if plugin:
                plugin.version = metadata.get('version', plugin.version)
                plugin.description = metadata.get('description', plugin.description)
                plugin.author = metadata.get('author', plugin.author)
                plugin.load_type = metadata.get('load_type', plugin.load_type)
                plugin.status = metadata.get('status', plugin.status)
                plugin.install_source = metadata.get('install_source', plugin.install_source)
                plugin.install_path = metadata.get('install_path', plugin.install_path)
                plugin.permissions = permissions if 'permissions' in metadata else plugin.permissions
                plugin.config_schema = config_schema if 'config_schema' in metadata else plugin.config_schema
                plugin.frontend_entry = metadata.get('frontend_entry', plugin.frontend_entry)
            else:
                plugin = Plugin(
                    name=name,
                    version=metadata.get('version', '0.0.0'),
                    description=metadata.get('description'),
                    author=metadata.get('author'),
                    load_type=metadata.get('load_type', 'hot'),
                    status=metadata.get('status', 'installed'),
                    install_source=metadata.get('install_source'),
                    install_path=metadata.get('install_path'),
                    permissions=permissions,
                    config_schema=config_schema,
                    frontend_entry=metadata.get('frontend_entry'),
                )
                db.add(plugin)

            db.commit()
            logger.info(f"插件已保存: name={name}")
            return True
        except Exception as e:
            db.rollback()
            logger.error(f"保存插件失败: name={metadata.get('name')}, error={e}")
            return False
        finally:
            db.close()

    @staticmethod
    def get_plugin(name: str) -> Optional[dict]:
        init_database_config()
        db: Session = SessionLocal()
        try:
            plugin = db.query(Plugin).filter_by(name=name).first()
            if not plugin:
                return None

            return {
                "name": plugin.name,
                "version": plugin.version,
                "description": plugin.description,
                "author": plugin.author,
                "load_type": plugin.load_type,
                "status": plugin.status,
                "install_source": plugin.install_source,
                "install_path": plugin.install_path,
                "permissions": _deserialize_json_field(plugin.permissions),
                "config_schema": _deserialize_json_field(plugin.config_schema),
                "frontend_entry": plugin.frontend_entry,
                "error_message": plugin.error_message,
                "installed_at": _format_datetime(plugin.installed_at),
                "updated_at": _format_datetime(plugin.updated_at),
            }
        except Exception as e:
            logger.error(f"获取插件失败: name={name}, error={e}")
            return None
        finally:
            db.close()

    @staticmethod
    def get_all_plugins() -> List[dict]:
        init_database_config()
        db: Session = SessionLocal()
        try:
            plugins = db.query(Plugin).all()
            result = []
            for plugin in plugins:
                result.append({
                    "name": plugin.name,
                    "version": plugin.version,
                    "description": plugin.description,
                    "author": plugin.author,
                    "load_type": plugin.load_type,
                    "status": plugin.status,
                    "install_source": plugin.install_source,
                    "install_path": plugin.install_path,
                    "permissions": _deserialize_json_field(plugin.permissions),
                    "config_schema": _deserialize_json_field(plugin.config_schema),
                    "frontend_entry": plugin.frontend_entry,
                    "error_message": plugin.error_message,
                    "installed_at": _format_datetime(plugin.installed_at),
                    "updated_at": _format_datetime(plugin.updated_at),
                })
            return result
        except Exception as e:
            logger.error(f"获取所有插件失败: error={e}")
            return []
        finally:
            db.close()

    @staticmethod
    def update_status(name: str, status: str, error_message: Optional[str] = None) -> bool:
        init_database_config()
        db: Session = SessionLocal()
        try:
            plugin = db.query(Plugin).filter_by(name=name).first()
            if not plugin:
                logger.error(f"更新插件状态失败: 插件不存在, name={name}")
                return False

            plugin.status = status
            plugin.error_message = error_message
            from datetime import datetime
            plugin.updated_at = datetime.now()
            db.commit()
            logger.info(f"插件状态已更新: name={name}, status={status}")
            return True
        except Exception as e:
            db.rollback()
            logger.error(f"更新插件状态失败: name={name}, error={e}")
            return False
        finally:
            db.close()

    @staticmethod
    def delete_plugin(name: str) -> bool:
        init_database_config()
        db: Session = SessionLocal()
        try:
            plugin = db.query(Plugin).filter_by(name=name).first()
            if not plugin:
                logger.error(f"删除插件失败: 插件不存在, name={name}")
                return False

            db.delete(plugin)
            db.commit()
            logger.info(f"插件已删除: name={name}")
            return True
        except Exception as e:
            db.rollback()
            logger.error(f"删除插件失败: name={name}, error={e}")
            return False
        finally:
            db.close()

    @staticmethod
    def update_plugin(name: str, **kwargs) -> bool:
        init_database_config()
        db: Session = SessionLocal()
        try:
            plugin = db.query(Plugin).filter_by(name=name).first()
            if not plugin:
                logger.error(f"更新插件失败: 插件不存在, name={name}")
                return False

            for key, value in kwargs.items():
                if hasattr(plugin, key):
                    if key in ('permissions', 'config_schema'):
                        setattr(plugin, key, _serialize_json_field(value))
                    else:
                        setattr(plugin, key, value)

            from datetime import datetime
            plugin.updated_at = datetime.now()
            db.commit()
            logger.info(f"插件已更新: name={name}")
            return True
        except Exception as e:
            db.rollback()
            logger.error(f"更新插件失败: name={name}, error={e}")
            return False
        finally:
            db.close()
