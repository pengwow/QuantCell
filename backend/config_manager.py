# 配置管理模块
# 用于加载和管理系统配置，避免循环导入

from loguru import logger
from collector.db import SystemConfigBusiness as SystemConfig


def load_system_configs():
    """从数据库加载所有系统配置
    
    Returns:
        dict: 包含所有系统配置的字典
    """
    try:
        logger.info("开始加载系统配置")
        configs = SystemConfig.get_all()
        logger.info(f"成功加载 {len(configs)} 项系统配置")
        return configs
    except Exception as e:
        logger.error(f"加载系统配置失败: {e}")
        logger.exception(e)
        return {}
