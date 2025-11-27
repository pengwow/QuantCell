# 数据库模型定义

from datetime import datetime
from typing import Optional, Dict, Any
from .connection import get_db_connection
from loguru import logger


class SystemConfig:
    """系统配置模型类
    
    用于操作system_config表，提供CRUD操作方法
    """
    
    @staticmethod
    def get(key: str) -> Optional[str]:
        """获取指定键的配置值
        
        Args:
            key: 配置键名
            
        Returns:
            Optional[str]: 配置值，如果不存在则返回None
        """
        try:
            conn = get_db_connection()
            result = conn.execute(
                "SELECT value FROM system_config WHERE key = ?",
                (key,)
            ).fetchone()
            return result[0] if result else None
        except Exception as e:
            logger.error(f"获取配置失败: key={key}, error={e}")
            return None
    
    @staticmethod
    def get_all() -> Dict[str, str]:
        """获取所有配置
        
        Returns:
            Dict[str, str]: 所有配置的字典，键为配置名，值为配置值
        """
        try:
            conn = get_db_connection()
            results = conn.execute(
                "SELECT key, value FROM system_config ORDER BY key"
            ).fetchall()
            return {row[0]: row[1] for row in results}
        except Exception as e:
            logger.error(f"获取所有配置失败: error={e}")
            return {}
    
    @staticmethod
    def set(key: str, value: str, description: Optional[str] = None) -> bool:
        """设置配置值
        
        Args:
            key: 配置键名
            value: 配置值
            description: 配置描述，可选
            
        Returns:
            bool: 设置成功返回True，失败返回False
        """
        try:
            conn = get_db_connection()
            # 使用UPSERT语法，存在则更新，不存在则插入
            conn.execute("""
            INSERT INTO system_config (key, value, description)
            VALUES (?, ?, ?)
            ON CONFLICT (key) DO UPDATE SET
                value = EXCLUDED.value,
                description = COALESCE(EXCLUDED.description, system_config.description)
            """, (key, value, description))
            logger.info(f"配置已更新: key={key}, value={value}")
            return True
        except Exception as e:
            logger.error(f"设置配置失败: key={key}, value={value}, error={e}")
            return False
    
    @staticmethod
    def delete(key: str) -> bool:
        """删除指定键的配置
        
        Args:
            key: 配置键名
            
        Returns:
            bool: 删除成功返回True，失败返回False
        """
        try:
            conn = get_db_connection()
            conn.execute("DELETE FROM system_config WHERE key = ?", (key,))
            logger.info(f"配置已删除: key={key}")
            return True
        except Exception as e:
            logger.error(f"删除配置失败: key={key}, error={e}")
            return False
    
    @staticmethod
    def get_with_details(key: str) -> Optional[Dict[str, Any]]:
        """获取配置的详细信息
        
        Args:
            key: 配置键名
            
        Returns:
            Optional[Dict[str, Any]]: 配置的详细信息，包括键、值、描述、创建时间和更新时间
        """
        try:
            conn = get_db_connection()
            result = conn.execute(
                "SELECT key, value, description, created_at, updated_at FROM system_config WHERE key = ?",
                (key,)
            ).fetchone()
            if result:
                return {
                    "key": result[0],
                    "value": result[1],
                    "description": result[2],
                    "created_at": result[3],
                    "updated_at": result[4]
                }
            return None
        except Exception as e:
            logger.error(f"获取配置详情失败: key={key}, error={e}")
            return None
    
    @staticmethod
    def get_all_with_details() -> Dict[str, Dict[str, Any]]:
        """获取所有配置的详细信息
        
        Returns:
            Dict[str, Dict[str, Any]]: 所有配置的详细信息，键为配置名，值为配置详情字典
        """
        try:
            conn = get_db_connection()
            results = conn.execute(
                "SELECT key, value, description, created_at, updated_at FROM system_config ORDER BY key"
            ).fetchall()
            return {
                row[0]: {
                    "key": row[0],
                    "value": row[1],
                    "description": row[2],
                    "created_at": row[3],
                    "updated_at": row[4]
                }
                for row in results
            }
        except Exception as e:
            logger.error(f"获取所有配置详情失败: error={e}")
            return {}
