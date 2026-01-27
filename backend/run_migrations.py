#!/usr/bin/env python3
"""
运行数据库迁移脚本

用于执行所有数据库表结构更新，确保表结构与模型定义保持一致
"""

import sys
import os

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from collector.db.migrations import run_migrations
from loguru import logger

if __name__ == "__main__":
    logger.info("开始执行数据库迁移...")
    try:
        run_migrations()
        logger.info("数据库迁移执行完成")
    except Exception as e:
        logger.error(f"数据库迁移失败: {e}")
        raise
