#!/usr/bin/env python3
"""更新特征信息脚本

定期执行脚本，读取数据目录中的特征文件，解析后将特征信息插入到数据库中
"""

import os
import sys
from pathlib import Path
from typing import Dict, List

from loguru import logger

# 添加项目根目录到Python路径
backend_root = Path(__file__).parent.parent
project_root = backend_root.parent  # 项目根目录是backend的父目录
sys.path.append(str(project_root))

# 配置日志
logger.add(
    backend_root / "logs" / "update_features.log",
    level="INFO",
    format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}",
    rotation="1 week",
    retention="4 weeks"
)


def load_features_from_dir(features_dir: Path) -> Dict[str, List[Dict[str, str]]]:
    """从目录中加载特征信息
    
    Args:
        features_dir: 特征目录路径
        
    Returns:
        Dict[str, List[Dict[str, str]]]: 特征信息字典，键为货币名称，值为特征列表
    """
    features = {}
    
    logger.info(f"开始从目录中加载特征信息: {features_dir}")
    
    # 检查目录是否存在
    if not features_dir.exists():
        logger.error(f"特征目录不存在: {features_dir}")
        return features
    
    # 遍历货币目录
    for symbol_dir in features_dir.iterdir():
        if symbol_dir.is_dir():
            symbol = symbol_dir.name
            logger.info(f"开始处理货币: {symbol}")
            
            # 获取该货币的所有特征文件
            feature_files = list(symbol_dir.glob("*.bin"))
            
            # 解析特征文件名
            symbol_features = []
            for f in feature_files:
                # 文件名格式：feature_name.freq.bin，如close.1h.bin
                file_name = f.stem  # 移除.bin扩展名，得到close.1h
                parts = file_name.split(".")
                if len(parts) >= 2:
                    # 最后一个部分是频率，前面的部分是特征名称
                    freq = parts[-1]
                    feature_name = ".".join(parts[:-1])
                    
                    symbol_features.append({
                        "feature_name": feature_name,
                        "freq": freq
                    })
                    logger.info(f"解析特征文件: {f.name} -> feature_name={feature_name}, freq={freq}")
            
            features[symbol] = symbol_features
            logger.info(f"货币{symbol}的特征处理完成，共{len(symbol_features)}个特征")
    
    logger.info(f"特征信息加载完成，共{len(features)}种货币")
    return features


def update_features_to_db(features: Dict[str, List[Dict[str, str]]]):
    """将特征信息更新到数据库中
    
    Args:
        features: 特征信息字典，键为货币名称，值为特征列表
    """
    logger.info("开始更新特征信息到数据库")
    
    try:
        # 导入数据库相关模块
        from sqlalchemy.orm import Session

        from collector.db import crud, models, schemas
        from collector.db.database import (SessionLocal, engine,
                                                   init_database_config)

        # 初始化数据库配置
        init_database_config()
        
        # 创建数据库会话
        db = SessionLocal()
        
        try:
            # 遍历所有货币的特征
            for symbol, symbol_features in features.items():
                logger.info(f"开始更新货币{symbol}的特征信息到数据库")
                
                # 批量创建新特征
                feature_create_list = []
                for f in symbol_features:
                    feature_create = schemas.FeatureCreate(
                        symbol=symbol,
                        feature_name=f["feature_name"],
                        freq=f["freq"]
                    )
                    feature_create_list.append(feature_create)
                
                # 在同一个事务中完成删除和插入操作
                # 先删除该货币的现有特征
                crud.delete_features_by_symbol(db, symbol)
                logger.info(f"已删除货币{symbol}的现有特征")
                
                # 批量创建特征
                if feature_create_list:
                    created_features = crud.create_features(db, feature_create_list)
                    logger.info(f"已创建货币{symbol}的{len(created_features)}个特征")
            
            logger.info("特征信息更新到数据库完成")
        except Exception as e:
            # 事务回滚
            db.rollback()
            raise
        finally:
            # 关闭数据库会话
            db.close()
    except Exception as e:
        logger.error(f"更新特征信息到数据库失败: {e}")
        logger.exception(e)
        raise


def main():
    """主函数
    """
    logger.info("开始执行更新特征信息脚本")
    
    try:
        # 从系统配置中获取qlib_data_dir
        from collector.db import SystemConfigBusiness as SystemConfig
        qlib_dir = SystemConfig.get("qlib_data_dir")
        
        if not qlib_dir:
            # 如果配置不存在，使用默认值
            qlib_dir = "data/qlib_data"
            logger.warning(f"未找到qlib_data_dir配置，使用默认值: {qlib_dir}")
        
        # 处理相对路径
        qlib_dir_path = Path(qlib_dir)
        if not qlib_dir_path.is_absolute():
            # 相对路径，基于backend目录
            qlib_dir_path = backend_root / qlib_dir_path
        
        qlib_dir_path = qlib_dir_path.expanduser().resolve()
        logger.info(f"QLib数据目录: {qlib_dir_path}")
        
        # 特征目录
        features_dir = qlib_dir_path / "features"
        logger.info(f"特征目录: {features_dir}")
        
        # 加载特征信息
        features = load_features_from_dir(features_dir)
        
        # 更新特征信息到数据库
        update_features_to_db(features)
        
        logger.info("更新特征信息脚本执行完成")
    except Exception as e:
        logger.error(f"更新特征信息脚本执行失败: {e}")
        logger.exception(e)
        # 不使用sys.exit(1)，避免导致整个应用程序崩溃
        # 只记录错误，让定时任务继续运行
        pass


if __name__ == "__main__":
    main()
