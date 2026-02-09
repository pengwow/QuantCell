# -*- coding: utf-8 -*-
"""
JWT安全密钥管理模块

实现JWT密钥的自动生成、安全存储和动态加载。
当配置文件中的密钥为空时，自动生成密码学安全的随机密钥。
"""

import os
import secrets
import shutil
from pathlib import Path
from typing import Optional

import tomli
import tomli_w
from loguru import logger


# 配置文件路径
CONFIG_FILE = Path(__file__).parent.parent / "config.toml"
BACKUP_FILE = Path(__file__).parent.parent / "config.toml.bak"

# 密钥配置项路径（在TOML中的位置）
SECRET_KEY_PATH = ["app", "secret_key"]


def generate_secure_key(length: int = 32) -> str:
    """
    生成密码学安全的随机密钥
    
    使用secrets模块生成URL安全的随机字符串，
    适用于JWT签名密钥。
    
    Args:
        length: 密钥字节长度，默认32字节（256位）
        
    Returns:
        str: Base64编码的随机密钥字符串
    """
    key = secrets.token_urlsafe(length)
    logger.info(f"已生成新的安全密钥（长度: {len(key)} 字符）")
    return key


def _get_nested_value(data: dict, path: list) -> Optional[str]:
    """
    从嵌套字典中获取值
    
    Args:
        data: 字典数据
        path: 键路径列表
        
    Returns:
        Optional[str]: 找到的值或None
    """
    current = data
    for key in path:
        if isinstance(current, dict) and key in current:
            current = current[key]
        else:
            return None
    return current


def _set_nested_value(data: dict, path: list, value: str) -> None:
    """
    在嵌套字典中设置值
    
    Args:
        data: 字典数据
        path: 键路径列表
        value: 要设置的值
    """
    current = data
    for key in path[:-1]:
        if key not in current:
            current[key] = {}
        current = current[key]
    current[path[-1]] = value


def _create_config_backup() -> bool:
    """
    创建配置文件备份
    
    Returns:
        bool: 备份是否成功
    """
    try:
        if CONFIG_FILE.exists():
            shutil.copy2(CONFIG_FILE, BACKUP_FILE)
            # 设置备份文件权限为只读
            os.chmod(BACKUP_FILE, 0o400)
            logger.info(f"配置文件已备份到: {BACKUP_FILE}")
        return True
    except Exception as e:
        logger.error(f"创建配置文件备份失败: {e}")
        return False


def _restore_config_backup() -> bool:
    """
    从备份恢复配置文件
    
    Returns:
        bool: 恢复是否成功
    """
    try:
        if BACKUP_FILE.exists():
            shutil.copy2(BACKUP_FILE, CONFIG_FILE)
            logger.info("配置文件已从备份恢复")
            return True
        return False
    except Exception as e:
        logger.error(f"恢复配置文件备份失败: {e}")
        return False


def _set_file_permissions(file_path: Path, mode: int = 0o600) -> bool:
    """
    设置文件权限
    
    Args:
        file_path: 文件路径
        mode: 权限模式，默认0o600（所有者可读写）
        
    Returns:
        bool: 设置是否成功
    """
    try:
        os.chmod(file_path, mode)
        logger.debug(f"文件权限已设置为 {oct(mode)}: {file_path}")
        return True
    except Exception as e:
        logger.warning(f"设置文件权限失败: {e}")
        return False


def load_config() -> dict:
    """
    加载配置文件
    
    Returns:
        dict: 配置数据字典
    """
    try:
        if not CONFIG_FILE.exists():
            logger.warning(f"配置文件不存在: {CONFIG_FILE}")
            return {}
        
        with open(CONFIG_FILE, "rb") as f:
            config = tomli.load(f)
        
        return config
    except Exception as e:
        logger.error(f"加载配置文件失败: {e}")
        return {}


def save_config(config: dict) -> bool:
    """
    保存配置到文件
    
    Args:
        config: 配置数据字典
        
    Returns:
        bool: 保存是否成功
    """
    try:
        # 创建备份
        if not _create_config_backup():
            logger.warning("无法创建备份，继续保存配置")
        
        # 写入配置 (tomli_w 需要二进制模式)
        with open(CONFIG_FILE, "wb") as f:
            tomli_w.dump(config, f)
        
        # 设置文件权限（仅所有者可读写）
        _set_file_permissions(CONFIG_FILE, 0o600)
        
        logger.info(f"配置已保存到: {CONFIG_FILE}")
        return True
    
    except Exception as e:
        logger.error(f"保存配置文件失败: {e}")
        # 尝试恢复备份
        _restore_config_backup()
        return False


def get_secret_key_from_config() -> Optional[str]:
    """
    从配置文件中获取secret_key
    
    Returns:
        Optional[str]: 密钥值，如果不存在或为空则返回None
    """
    config = load_config()
    key_value = _get_nested_value(config, SECRET_KEY_PATH)
    
    if key_value and str(key_value).strip():
        return str(key_value).strip()
    
    return None


def is_secret_key_configured() -> bool:
    """
    检查密钥是否已配置
    
    Returns:
        bool: 密钥是否已配置且不为空
    """
    key = get_secret_key_from_config()
    return key is not None and len(key) > 0


def generate_and_save_secret_key() -> Optional[str]:
    """
    生成新密钥并保存到配置文件
    
    Returns:
        Optional[str]: 生成的密钥，失败则返回None
    """
    try:
        # 生成新密钥
        new_key = generate_secure_key()
        
        # 加载当前配置
        config = load_config()
        
        # 设置新密钥
        _set_nested_value(config, SECRET_KEY_PATH, new_key)
        
        # 保存配置
        if save_config(config):
            logger.info("JWT安全密钥已自动生成并保存到配置文件")
            return new_key
        else:
            logger.error("保存密钥到配置文件失败")
            return None
    
    except Exception as e:
        logger.error(f"生成和保存密钥失败: {e}")
        return None


def get_or_create_secret_key() -> str:
    """
    获取或创建JWT安全密钥
    
    这是主要的公共接口：
    - 如果配置文件中已有密钥，直接返回
    - 如果密钥为空或不存在，自动生成并保存新密钥
    
    Returns:
        str: JWT安全密钥
    """
    # 首先尝试从配置读取
    existing_key = get_secret_key_from_config()
    
    if existing_key:
        logger.debug("使用配置文件中现有的JWT密钥")
        return existing_key
    
    # 密钥不存在或为空，生成新密钥
    logger.warning("配置文件中的JWT密钥为空，正在自动生成新密钥...")
    new_key = generate_and_save_secret_key()
    
    if new_key:
        return new_key
    
    # 如果生成失败，使用临时密钥（仅用于避免系统崩溃）
    logger.error("无法生成或保存密钥，使用临时密钥（请立即检查配置！）")
    return secrets.token_urlsafe(32)


def initialize_secret_key() -> str:
    """
    初始化JWT密钥
    
    在应用启动时调用，确保密钥已就绪。
    
    Returns:
        str: JWT安全密钥
    """
    logger.info("正在初始化JWT安全密钥...")
    key = get_or_create_secret_key()
    
    # 验证密钥长度
    if len(key) < 16:
        logger.warning("JWT密钥长度较短，建议至少32字节")
    
    logger.info("JWT安全密钥初始化完成")
    return key


# 全局密钥缓存（避免重复读取文件）
_cached_secret_key: Optional[str] = None


def get_secret_key() -> str:
    """
    获取JWT密钥（带缓存）
    
    优先使用缓存的密钥，避免频繁读取配置文件。
    
    Returns:
        str: JWT安全密钥
    """
    global _cached_secret_key
    
    if _cached_secret_key is None:
        _cached_secret_key = get_or_create_secret_key()
    
    return _cached_secret_key


def clear_secret_key_cache() -> None:
    """
    清除密钥缓存
    
    在密钥更新后调用，强制下次重新读取配置。
    """
    global _cached_secret_key
    _cached_secret_key = None
    logger.debug("JWT密钥缓存已清除")
