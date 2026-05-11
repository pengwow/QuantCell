#!/usr/bin/env python3
# 命令行工具，用于导出数据库中的K线数据到CSV文件

import os
import sys
from pathlib import Path

import typer
from utils.logger import get_logger, LogType

# 获取模块日志器
logger = get_logger(__name__, LogType.APPLICATION)
# 添加项目根目录到Python路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from collector.scripts.export_data import ExportData


# 创建 typer 应用实例
app = typer.Typer(help="命令行工具，用于导出数据库中的K线数据到CSV文件")


@app.command("crypto")
def crypto(
    symbols: str = typer.Argument(..., help="交易对列表，使用逗号分隔，如BTCUSDT,ETHUSDT"),
    interval: str = typer.Option("1d", help="时间间隔，如1d, 1h, 15m等"),
    start: str = typer.Option(..., help="开始时间 (YYYY-MM-DD)"),
    end: str = typer.Option(..., help="结束时间 (YYYY-MM-DD)"),
    exchange: str = typer.Option("binance", help="交易所 (binance/okx)"),
    candle_type: str = typer.Option("spot", help="蜡烛图类型 (spot/futures)"),
    save_dir: Path = typer.Option(None, help="保存目录"),
    max_workers: int = typer.Option(1, help="最大工作线程数"),
    auto_download: bool = typer.Option(True, help="是否自动下载缺失数据"),
):
    """导出加密货币K线数据到CSV文件"""
    
    # 解析交易对列表
    if isinstance(symbols, str):
        symbols_list = symbols.split(',')
    else:
        symbols_list = [symbols]
    
    # 初始化导出工具
    export_data = ExportData()
    
    # 执行导出
    result = export_data.export_kline_data(
        symbols=symbols_list,
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


if __name__ == "__main__":
    # 配置日志格式
    logger.add(
        "export_kline.log",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}",
        level="INFO",
        rotation="1 week",
        retention="1 month",
    )
    
    # 使用typer运行应用
    app()
