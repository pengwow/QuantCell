#!/usr/bin/env python3
"""测试 update_features.py 脚本

用于验证 update_features.py 脚本的功能，特别是路径处理和特征信息加载
"""

import os
import sys
from pathlib import Path

# 添加项目根目录到Python路径
backend_root = Path(__file__).parent
project_root = backend_root.parent  # 项目根目录是backend的父目录

sys.path.append(str(project_root))  # 添加项目根目录


# 配置日志
from loguru import logger

logger.remove()
logger.add(sys.stdout, level="INFO", format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}")

def test_path_handling():
    """测试路径处理逻辑"""
    logger.info("开始测试路径处理逻辑")
    
    # 测试 SystemConfigBusiness 类
    from collector.db import SystemConfigBusiness as SystemConfig
    logger.info("测试 SystemConfig.get() 方法")
    
    # 获取 qlib_data_dir 配置
    qlib_dir = SystemConfig.get("qlib_data_dir")
    logger.info(f"SystemConfig.get('qlib_data_dir') 返回: {qlib_dir}")
    
    # 测试路径处理
    qlib_dir_path = Path(qlib_dir)
    logger.info(f"qlib_dir_path.is_absolute(): {qlib_dir_path.is_absolute()}")
    
    if not qlib_dir_path.is_absolute():
        # 相对路径，基于backend目录
        qlib_dir_path = backend_root / qlib_dir_path
        logger.info(f"处理后的绝对路径: {qlib_dir_path}")
    
    qlib_dir_path = qlib_dir_path.expanduser().resolve()
    logger.info(f"最终解析路径: {qlib_dir_path}")
    
    # 测试特征目录
    features_dir = qlib_dir_path / "features"
    logger.info(f"特征目录: {features_dir}")
    logger.info(f"特征目录是否存在: {features_dir.exists()}")
    
    if features_dir.exists():
        logger.info("特征目录内容:")
        for item in features_dir.iterdir():
            if item.is_dir():
                logger.info(f"  - 货币目录: {item.name}")
                # 列出该货币目录下的前几个文件
                try:
                    files = list(item.iterdir())[:5]
                    for f in files:
                        logger.info(f"    - 文件: {f.name}")
                    if len(list(item.iterdir())) > 5:
                        logger.info(f"    - ... 等共{len(list(item.iterdir()))}个文件")
                except Exception as e:
                    logger.error(f"    - 读取目录失败: {e}")
    
    return features_dir

def test_feature_parsing():
    """测试特征文件解析"""
    logger.info("\n开始测试特征文件解析")
    
    # 导入脚本中的函数
    # 从配置获取 qlib_dir
    from collector.db import SystemConfigBusiness as SystemConfig
    from scripts.update_features import load_features_from_dir
    qlib_dir = SystemConfig.get("qlib_data_dir")
    qlib_dir_path = Path(qlib_dir)
    
    if not qlib_dir_path.is_absolute():
        qlib_dir_path = backend_root / qlib_dir_path
    
    qlib_dir_path = qlib_dir_path.expanduser().resolve()
    features_dir = qlib_dir_path / "features"
    
    logger.info(f"测试加载特征: {features_dir}")
    features = load_features_from_dir(features_dir)
    
    logger.info(f"加载到的特征数量: {len(features)}")
    for symbol, symbol_features in features.items():
        logger.info(f"货币 {symbol} 有 {len(symbol_features)} 个特征")
        for f in symbol_features[:5]:  # 只显示前5个特征
            logger.info(f"  - {f['feature_name']} ({f['freq']})")
        if len(symbol_features) > 5:
            logger.info(f"  - ... 等共{len(symbol_features)}个特征")
    
    return features

def test_db_update():
    """测试数据库更新"""
    logger.info("\n开始测试数据库更新")
    
    # 先获取一些测试数据
    from collector.db import SystemConfigBusiness as SystemConfig
    from scripts.update_features import (load_features_from_dir,
                                         update_features_to_db)
    
    qlib_dir = SystemConfig.get("qlib_data_dir")
    qlib_dir_path = Path(qlib_dir)
    
    if not qlib_dir_path.is_absolute():
        qlib_dir_path = backend_root / qlib_dir_path
    
    qlib_dir_path = qlib_dir_path.expanduser().resolve()
    features_dir = qlib_dir_path / "features"
    
    features = load_features_from_dir(features_dir)
    
    if features:
        logger.info(f"准备更新 {len(features)} 种货币的特征到数据库")
        update_features_to_db(features)
        logger.info("数据库更新完成")
    else:
        logger.warning("没有加载到特征数据，跳过数据库更新测试")
    
    # 验证数据库中的数据
    logger.info("验证数据库中的特征数据")
    from sqlalchemy.orm import Session

    from collector.db import crud, models
    from collector.db.database import engine
    
    db = Session(bind=engine)
    try:
        # 获取所有特征
        all_features = crud.get_features(db)
        logger.info(f"数据库中共有 {len(all_features)} 个特征记录")
        
        # 按货币分组统计
        features_by_symbol = {}
        for f in all_features:
            if f.symbol not in features_by_symbol:
                features_by_symbol[f.symbol] = []
            features_by_symbol[f.symbol].append(f)
        
        logger.info(f"数据库中共有 {len(features_by_symbol)} 种货币的特征")
        for symbol, symbol_features in features_by_symbol.items():
            logger.info(f"货币 {symbol}: {len(symbol_features)} 个特征")
    finally:
        db.close()

if __name__ == "__main__":
    logger.info("开始测试 update_features.py 脚本")
    
    # 测试1: 路径处理
    test_path_handling()
    
    # 测试2: 特征解析
    test_feature_parsing()
    
    # 测试3: 数据库更新
    test_db_update()
    
    logger.info("所有测试完成")
