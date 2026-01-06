#!/usr/bin/env python3
# 命令行工具，用于导出数据库中的K线数据到CSV文件

import os
import sys
from pathlib import Path

import fire
from loguru import logger

# 添加项目根目录到Python路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from backend.collector.scripts.export_data import ExportData


class ExportKline:
    """命令行工具，用于导出数据库中的K线数据到CSV文件"""
    
    def __init__(self):
        """初始化命令行工具"""
        self.export_data = ExportData()
    
    def crypto(self, symbols, interval, start, end, 
              exchange="binance", candle_type="spot", 
              save_dir=None, max_workers=1, auto_download=True):
        """导出加密货币K线数据到CSV文件
        
        Args:
            symbols: 交易对列表，使用逗号分隔，如BTCUSDT,ETHUSDT
            interval: 时间间隔，如1d, 1h, 15m等
            start: 开始时间，格式为YYYY-MM-DD或YYYY-MM-DD HH:MM:SS
            end: 结束时间，格式为YYYY-MM-DD或YYYY-MM-DD HH:MM:SS
            exchange: 交易所，默认binance
            candle_type: 蜡烛图类型，spot或futures，默认spot
            save_dir: 保存目录，默认使用~/.qlib/crypto_data/export
            max_workers: 最大工作线程数，默认1
            auto_download: 是否自动下载缺失数据，默认True
        """
        # 解析交易对列表
        if isinstance(symbols, str):
            symbols = symbols.split(',')
        
        # 执行导出
        result = self.export_data.export_kline_data(
            symbols=symbols,
            interval=interval,
            start=start,
            end=end,
            exchange=exchange,
            candle_type=candle_type,
            save_dir=save_dir,
            max_workers=max_workers,
            auto_download=auto_download
        )
        
        # 输出结果
        if result["success"]:
            logger.info(f"导出成功，共导出 {len(result['exported_files'])} 个文件")
            for file_path in result["exported_files"]:
                logger.info(f"- {file_path}")
            
            if result["missing_ranges"]:
                logger.warning(f"以下交易对存在缺失数据范围:")
                for symbol, ranges in result["missing_ranges"].items():
                    logger.warning(f"- {symbol}:")
                    for r in ranges:
                        logger.warning(f"  * {r['start']} 至 {r['end']}")
        else:
            logger.error(f"导出失败")
            if result["missing_ranges"]:
                logger.error(f"错误详情:")
                for symbol, ranges in result["missing_ranges"].items():
                    logger.error(f"- {symbol}:")
                    for r in ranges:
                        if "error" in r:
                            logger.error(f"  * 错误: {r['error']}")
                        else:
                            logger.error(f"  * {r['start']} 至 {r['end']}")
        
        return result
    
    def help(self):
        """显示帮助信息"""
        print("K线数据导出工具使用说明：")
        print("\n1. 导出加密货币K线数据：")
        print("   python export_kline.py crypto --symbols BTCUSDT,ETHUSDT --interval 1d --start 2024-01-01 --end 2024-12-31")
        print("\n2. 导出加密货币K线数据到指定目录：")
        print("   python export_kline.py crypto --symbols BTCUSDT --interval 1h --start 2024-01-01 --end 2024-01-02 --save_dir /path/to/save")
        print("\n3. 不自动下载缺失数据：")
        print("   python export_kline.py crypto --symbols BTCUSDT --interval 1d --start 2024-01-01 --end 2024-12-31 --auto_download false")
        print("\n4. 使用多个工作线程：")
        print("   python export_kline.py crypto --symbols BTCUSDT,ETHUSDT --interval 1d --start 2024-01-01 --end 2024-12-31 --max_workers 4")
        print("\n5. 导出期货数据：")
        print("   python export_kline.py crypto --symbols BTCUSDT --interval 1d --start 2024-01-01 --end 2024-12-31 --candle_type futures")
        print("\n6. 查看详细帮助：")
        print("   python export_kline.py crypto --help")


if __name__ == "__main__":
    # 配置日志格式
    logger.add(
        "export_kline.log",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}",
        level="INFO",
        rotation="1 week",
        retention="1 month",
    )
    
    # 使用fire库创建命令行界面
    fire.Fire(ExportKline)
