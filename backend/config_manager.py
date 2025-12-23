# 配置管理模块
# 用于加载和管理系统配置，避免循环导入

from loguru import logger


def load_system_configs():
    """从数据库加载所有系统配置
    
    Returns:
        dict: 包含所有系统配置的字典
    """
    try:
        logger.info("开始加载系统配置")
        # 延迟导入，避免循环导入
        from backend.collector.db.models import \
            SystemConfigBusiness as SystemConfig
        configs = SystemConfig.get_all()
        logger.info(f"成功加载 {len(configs)} 项系统配置")
        return configs
    except Exception as e:
        logger.error(f"加载系统配置失败: {e}")
        logger.exception(e)
        return {}


def get_config(key, default=None):
    """获取指定配置项的值
    
    Args:
        key: 配置项键名
        default: 默认值，如果配置项不存在则返回默认值
    
    Returns:
        配置项的值或默认值
    """
    try:
        configs = load_system_configs()
        return configs.get(key, default)
    except Exception as e:
        logger.error(f"获取配置失败: {e}")
        logger.exception(e)
        # 出错时返回默认值
        return default
