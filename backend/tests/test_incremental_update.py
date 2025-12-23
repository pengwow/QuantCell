#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试加密货币数据的增量更新功能

该脚本用于测试加密货币数据的增量更新功能，包括：
1. 数据入库功能
2. 增量更新功能（只下载缺失的数据）
"""

import os
import sys

# 添加当前目录到Python路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, timedelta

import pandas as pd
from loguru import logger

from collector.crypto.binance.collector import BinanceCollector
from collector.db.models import SystemConfigBusiness as SystemConfig


def test_data_write_to_db():
    """
    测试数据入库功能
    
    1. 设置data_write_to_db为true
    2. 下载少量数据
    3. 检查数据是否写入数据库
    
    Returns:
        bool: 测试是否通过
    """
    logger.info("=== 开始测试数据入库功能 ===")
    
    try:
        # 初始化数据库，创建表
        from collector.db import init_db
        init_db()
        logger.info("数据库初始化完成")
        
        # 设置data_write_to_db为true
        SystemConfig.set("data_write_to_db", "true", "是否将下载的数据写入数据库")
        logger.info("已设置data_write_to_db为true")
        
        # 创建收集器实例
        collector = BinanceCollector(
            save_dir="./test_data",
            start="2024-01-01",
            end="2024-01-03",
            interval="1d",
            symbols=["BTCUSDT"],
            max_workers=1
        )
        
        # 执行数据收集
        collector.collect_data()
        logger.info("数据收集完成")
        
        # 检查数据库中是否有数据
        from collector.db.database import SessionLocal
        from collector.db.models import Kline
        
        db = SessionLocal()
        try:
            # 查询数据
            kline_count = db.query(Kline).filter(
                Kline.symbol == "BTCUSDT",
                Kline.interval == "1d"
            ).count()
            
            logger.info(f"数据库中BTCUSDT 1d数据条数: {kline_count}")
            
            if kline_count > 0:
                logger.info("✅ 数据入库功能测试通过")
                return True
            else:
                logger.error("❌ 数据入库功能测试失败：数据库中没有数据")
                return False
        finally:
            db.close()
    except Exception as e:
        logger.error(f"❌ 数据入库功能测试失败：{e}")
        logger.exception(e)
        return False


def test_incremental_update():
    """
    测试增量更新功能
    
    1. 先下载一段时间的数据
    2. 然后使用增量更新模式下载更长时间的数据
    3. 检查是否只下载了缺失的数据
    
    Returns:
        bool: 测试是否通过
    """
    logger.info("=== 开始测试增量更新功能 ===")
    
    try:
        # 确保data_write_to_db为true
        SystemConfig.set("data_write_to_db", "true", "是否将下载的数据写入数据库")
        
        # 1. 第一次下载：2024-01-01 到 2024-01-03
        logger.info("第一次下载：2024-01-01 到 2024-01-03")
        collector1 = BinanceCollector(
            save_dir="./test_data",
            start="2024-01-01",
            end="2024-01-03",
            interval="1d",
            symbols=["BTCUSDT"],
            max_workers=1
        )
        collector1.collect_data()
        
        # 2. 第二次下载：使用增量更新模式，下载2024-01-01 到 2024-01-05
        logger.info("第二次下载：使用增量更新模式，下载2024-01-01 到 2024-01-05")
        collector2 = BinanceCollector(
            save_dir="./test_data",
            start="2024-01-01",
            end="2024-01-05",
            interval="1d",
            symbols=["BTCUSDT"],
            max_workers=1
        )
        # 设置update_mode为true
        collector2.update_mode = True
        collector2.collect_data()
        
        # 3. 检查数据库中数据的时间范围
        from collector.db.database import SessionLocal
        from collector.db.models import Kline
        
        db = SessionLocal()
        try:
            # 查询数据的时间范围
            min_date = db.query(Kline.date).filter(
                Kline.symbol == "BTCUSDT",
                Kline.interval == "1d"
            ).order_by(Kline.date.asc()).first()
            
            max_date = db.query(Kline.date).filter(
                Kline.symbol == "BTCUSDT",
                Kline.interval == "1d"
            ).order_by(Kline.date.desc()).first()
            
            logger.info(f"数据库中BTCUSDT 1d数据时间范围：{min_date[0]} 到 {max_date[0]}")
            
            # 检查是否包含2024-01-04和2024-01-05的数据
            expected_min_date = pd.Timestamp("2024-01-01")
            expected_max_date = pd.Timestamp("2024-01-05")
            
            if min_date[0] <= expected_min_date and max_date[0] >= expected_max_date:
                logger.info("✅ 增量更新功能测试通过")
                return True
            else:
                logger.error(f"❌ 增量更新功能测试失败：数据时间范围不符合预期")
                return False
        finally:
            db.close()
    except Exception as e:
        logger.error(f"❌ 增量更新功能测试失败：{e}")
        logger.exception(e)
        return False


def test_full_download():
    """
    测试全量下载功能（update_mode=False）
    
    Returns:
        bool: 测试是否通过
    """
    logger.info("=== 开始测试全量下载功能 ===")
    
    try:
        # 创建收集器实例，update_mode默认为False
        collector = BinanceCollector(
            save_dir="./test_data",
            start="2024-01-01",
            end="2024-01-02",
            interval="1h",
            symbols=["ETHUSDT"],
            max_workers=1
        )
        
        # 执行数据收集
        collector.collect_data()
        logger.info("数据收集完成")
        
        # 检查数据库中是否有数据
        from collector.db.database import SessionLocal
        from collector.db.models import Kline
        
        db = SessionLocal()
        try:
            # 查询数据
            kline_count = db.query(Kline).filter(
                Kline.symbol == "ETHUSDT",
                Kline.interval == "1h"
            ).count()
            
            logger.info(f"数据库中ETHUSDT 1h数据条数: {kline_count}")
            
            if kline_count > 0:
                logger.info("✅ 全量下载功能测试通过")
                return True
            else:
                logger.error("❌ 全量下载功能测试失败：数据库中没有数据")
                return False
        finally:
            db.close()
    except Exception as e:
        logger.error(f"❌ 全量下载功能测试失败：{e}")
        logger.exception(e)
        return False


if __name__ == "__main__":
    """
    主函数，执行所有测试
    """
    logger.info("开始测试加密货币数据下载功能")
    
    # 设置日志级别
    logger.remove()
    logger.add(sys.stdout, level="INFO")
    
    # 执行测试
    results = []
    
    # 测试数据入库功能
    results.append("数据入库功能: " + ("✅ 成功" if test_data_write_to_db() else "❌ 失败"))
    
    # 测试全量下载功能
    results.append("全量下载功能: " + ("✅ 成功" if test_full_download() else "❌ 失败"))
    
    # 测试增量更新功能
    results.append("增量更新功能: " + ("✅ 成功" if test_incremental_update() else "❌ 失败"))
    
    # 打印测试结果
    logger.info("\n=== 测试结果汇总 ===")
    for result in results:
        logger.info(result)
    
    # 统计成功次数
    success_count = sum(1 for result in results if "✅" in result)
    total_count = len(results)
    
    logger.info(f"\n总测试数: {total_count}, 成功: {success_count}, 失败: {total_count - success_count}")
    
    # 退出状态码
    sys.exit(0 if success_count == total_count else 1)
