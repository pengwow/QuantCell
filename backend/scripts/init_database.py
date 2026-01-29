#!/usr/bin/env python3
"""
数据库初始化脚本

用于在程序安装过程中执行全量数据库表初始化操作
支持SQLite和DuckDB数据库
"""
import os
import sys
from pathlib import Path
import logging
from loguru import logger

# 添加项目根目录到Python路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent))

# 先导入基础模块，避免循环导入
from collector.db.database import init_database_config, Base

# 延迟导入模型，避免导入错误
SystemConfig = None
Task = None
Feature = None
DataPool = None
DataPoolAsset = None
CryptoSymbol = None
CryptoSpotKline = None
CryptoFutureKline = None
StockKline = None
ScheduledTask = None
BacktestTask = None
BacktestResult = None
Strategy = None

def load_models():
    """延迟加载模型，避免导入错误"""
    global SystemConfig, Task, Feature, DataPool, DataPoolAsset
    global CryptoSymbol, CryptoSpotKline, CryptoFutureKline, StockKline
    global ScheduledTask, BacktestTask, BacktestResult, Strategy
    
    from collector.db.models import (
        SystemConfig as SC,
        Task as T,
        Feature as F,
        DataPool as DP,
        DataPoolAsset as DPA,
        CryptoSymbol as CS,
        CryptoSpotKline as CSK,
        CryptoFutureKline as CFK,
        StockKline as SK,
        ScheduledTask as ST,
        BacktestTask as BT,
        BacktestResult as BR,
        Strategy as S
    )
    
    SystemConfig = SC
    Task = T
    Feature = F
    DataPool = DP
    DataPoolAsset = DPA
    CryptoSymbol = CS
    CryptoSpotKline = CSK
    CryptoFutureKline = CFK
    StockKline = SK
    ScheduledTask = ST
    BacktestTask = BT
    BacktestResult = BR
    Strategy = S

def setup_logging():
    """设置日志配置"""
    logger.remove()
    logger.add(
        sys.stdout,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
        level="INFO"
    )
    # 同时记录到文件
    log_file = Path(__file__).parent.parent / "logs" / "init_database.log"
    log_file.parent.mkdir(exist_ok=True)
    logger.add(
        str(log_file),
        rotation="10 MB",
        retention="7 days",
        compression="zip",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}"
    )

def init_database():
    """初始化数据库
    
    1. 初始化数据库配置
    2. 加载数据模型
    3. 创建所有表结构
    4. 处理数据库兼容性问题
    5. 记录执行结果
    """
    try:
        logger.info("开始数据库初始化...")
        
        # 初始化数据库配置
        init_database_config()
        logger.info("数据库配置初始化成功")
        
        # 加载数据模型
        logger.info("加载数据模型...")
        load_models()
        logger.info("数据模型加载成功")
        
        # 获取所有模型类
        models = [
            SystemConfig,
            Task,
            Feature,
            DataPool,
            DataPoolAsset,
            CryptoSymbol,
            CryptoSpotKline,
            CryptoFutureKline,
            StockKline,
            ScheduledTask,
            BacktestTask,
            BacktestResult,
            Strategy
        ]
        
        logger.info(f"找到 {len(models)} 个数据模型")
        
        # 创建表结构
        logger.info("开始创建数据库表结构...")
        from collector.db.database import engine
        Base.metadata.create_all(engine, checkfirst=True)
        logger.info("数据库表结构创建完成")
        
        # 验证表是否创建成功
        logger.info("验证表结构...")
        from sqlalchemy import inspect
        from collector.db.database import engine
        
        inspector = inspect(engine)
        existing_tables = inspector.get_table_names()
        logger.info(f"数据库中存在 {len(existing_tables)} 个表: {existing_tables}")
        
        # 检查关键表是否存在
        key_tables = ["system_config", "crypto_symbols", "crypto_spot_klines"]
        for table in key_tables:
            if table in existing_tables:
                logger.info(f"关键表 {table} 存在")
            else:
                logger.warning(f"关键表 {table} 不存在")
        
        # 检查crypto_symbols表是否有is_deleted字段
        if "crypto_symbols" in existing_tables:
            columns = [col['name'] for col in inspector.get_columns("crypto_symbols")]
            if "is_deleted" in columns:
                logger.info("crypto_symbols表已包含is_deleted字段")
            else:
                logger.warning("crypto_symbols表缺少is_deleted字段，建议运行迁移脚本")
        
        # 将config.toml配置写入系统配置表
        logger.info("开始写入配置到系统配置表...")
        try:
            # 导入配置管理器
            import sys
            sys.path.insert(0, str(Path(__file__).parent.parent))
            from utils.config_manager import config_manager
            from collector.db.models import SystemConfigBusiness
            
            # 使用配置管理器读取配置文件
            config_data = config_manager.read_config()
            
            logger.info("读取到配置文件")
            
            # 定义配置分组映射
            config_group_mapping = {
                'database': 'database',
                'app': 'app',
                'quant': 'quant',
                'basic_settings': 'basic',
                'notification_settings': 'notifications',
                'api_settings': 'api',
                'system_config': 'system'
            }
            
            # 遍历所有配置分组
            for group_name, group_config in config_data.items():
                # 检查是否为嵌套分组（如exchanges.binance）
                if isinstance(group_config, dict):
                    # 检查是否需要特殊处理
                    if group_name in config_group_mapping:
                        # 使用映射的分组名称
                        mapped_group = config_group_mapping[group_name]
                        logger.info(f"处理配置分组: {group_name} -> {mapped_group}")
                        
                        # 遍历分组内的配置项
                        for key, value in group_config.items():
                            # 检查value是否为嵌套字典（如exchanges.binance）
                            if isinstance(value, dict):
                                # 处理嵌套分组
                                for nested_key, nested_value in value.items():
                                    # 直接使用原始key，不进行拼接
                                    SystemConfigBusiness.set(nested_key, str(nested_value), name=group_name)
                                    logger.debug(f"写入配置项: {nested_key} = {nested_value} (name={group_name})")
                            else:
                                # 处理普通配置项
                                # 直接使用原始key，不进行拼接
                                SystemConfigBusiness.set(key, str(value), name=group_name)
                                logger.debug(f"写入配置项: {key} = {value} (name={group_name})")
                        
                        logger.info(f"{group_name}配置写入完成")
                    else:
                        # 处理未映射的分组
                        logger.info(f"处理未映射的配置分组: {group_name}")
                        
                        # 遍历分组内的配置项
                        for key, value in group_config.items():
                            # 直接使用原始key，不进行拼接
                            SystemConfigBusiness.set(key, str(value), name=group_name)
                            logger.debug(f"写入配置项: {key} = {value} (name={group_name})")
                        
                        logger.info(f"{group_name}配置写入完成")
            
            logger.info("配置写入系统配置表完成")
        except Exception as e:
            logger.error(f"写入配置到系统配置表失败: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
        
        logger.info("数据库初始化完成！")
        return True
        
    except Exception as e:
        logger.error(f"数据库初始化失败: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return False

def main():
    """主函数"""
    setup_logging()
    
    logger.info("=====================================")
    logger.info("        数据库初始化脚本")
    logger.info("=====================================")
    
    # 显示当前配置
    logger.info(f"当前工作目录: {os.getcwd()}")
    logger.info(f"脚本路径: {Path(__file__).absolute()}")
    
    # 执行初始化
    success = init_database()
    
    if success:
        logger.info("数据库初始化成功！")
        sys.exit(0)
    else:
        logger.error("数据库初始化失败！")
        sys.exit(1)

if __name__ == "__main__":
    main()
