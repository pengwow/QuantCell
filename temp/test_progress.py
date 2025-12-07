#!/usr/bin/env python3
"""
测试Binance下载器的进度更新功能
"""

import sys
from pathlib import Path

# 添加项目根目录到Python路径
sys.path.append(str(Path(__file__).parent.parent))

from loguru import logger
from backend.collector.crypto.binance.collector import BinanceCollector

# 配置日志
logger.remove()
logger.add(sys.stdout, level="INFO", format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}")

# 定义进度回调函数
def progress_callback(symbol, current, total, status):
    """
    进度回调函数
    
    :param symbol: 交易对
    :param current: 当前进度
    :param total: 总进度
    :param status: 状态信息
    """
    progress = (current / total) * 100 if total > 0 else 0
    print(f"\r进度: {symbol} {progress:.1f}% ({current}/{total}) - {status}", end="", flush=True)

# 测试进度更新功能
def test_progress_update():
    """测试进度更新功能"""
    logger.info("开始测试进度更新功能")
    
    # 创建收集器实例
    collector = BinanceCollector(
        save_dir="./test_data",
        start="2025-11-01",
        end="2025-11-05",  # 只下载5天数据，便于测试
        interval="1h",
        candle_type="spot",
        symbols=["BTCUSDT"],  # 只下载BTCUSDT，便于测试
        max_workers=1
    )
    
    # 执行数据收集，传入进度回调函数
    logger.info("开始收集数据...")
    collector.collect_data(progress_callback=progress_callback)
    
    logger.info("\n数据收集完成，进度测试结束")

if __name__ == "__main__":
    test_progress_update()