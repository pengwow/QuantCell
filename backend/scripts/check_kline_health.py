#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
K线数据健康检查脚本

基于 Typer 的命令行工具，用于检查数据库中kline表数据的健康状况
"""

from datetime import datetime
from typing import Optional

import typer
from loguru import logger

from backend.collector.services.kline_health_service import KlineHealthChecker

app = typer.Typer(help="K线数据健康检查工具")


@app.command()
def check(
    symbol: str = typer.Argument(..., help="货币对，如BTCUSDT"),
    interval: str = typer.Argument(..., help="时间周期，如1m, 5m, 1h, 1d"),
    start: Optional[str] = typer.Option(None, "--start", "-s", help="开始时间，格式为YYYY-MM-DD HH:MM:SS或YYYY-MM-DD"),
    end: Optional[str] = typer.Option(None, "--end", "-e", help="结束时间，格式为YYYY-MM-DD HH:MM:SS或YYYY-MM-DD"),
    market_type: str = typer.Option("crypto", "--market", "-m", help="市场类型，如crypto（加密货币）、stock（股票）、futures（期货）"),
    crypto_type: str = typer.Option("spot", "--crypto-type", "-c", help="加密货币类型，如spot（现货）、future（合约）"),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="输出结果到JSON文件"),
):
    """
    执行K线数据健康检查
    
    示例:
        python check_kline_health.py BTCUSDT 1m
        python check_kline_health.py BTCUSDT 1h --start 2024-01-01 --end 2024-01-31
        python check_kline_health.py ETHUSDT 15m --market crypto --crypto-type future
    """
    # 解析时间参数
    start_dt = None
    end_dt = None
    
    if start:
        try:
            start_dt = datetime.fromisoformat(start)
        except ValueError:
            try:
                start_dt = datetime.strptime(start, "%Y-%m-%d")
            except ValueError:
                logger.error(f"无效的开始时间格式: {start}")
                raise typer.Exit(1)
    
    if end:
        try:
            end_dt = datetime.fromisoformat(end)
        except ValueError:
            try:
                end_dt = datetime.strptime(end, "%Y-%m-%d")
            except ValueError:
                logger.error(f"无效的结束时间格式: {end}")
                raise typer.Exit(1)
    
    # 执行健康检查
    checker = KlineHealthChecker()
    result = checker.check_all(symbol, interval, start_dt, end_dt, market_type, crypto_type)
    
    # 输出结果
    import json
    print(json.dumps(result, indent=2, ensure_ascii=False))
    
    # 保存到文件（如果指定了输出路径）
    if output:
        with open(output, 'w', encoding='utf-8') as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        logger.info(f"结果已保存到: {output}")
    
    # 根据检查结果返回退出码
    if result["overall_status"] == "fail":
        raise typer.Exit(1)


@app.command()
def batch_check(
    symbols: list[str] = typer.Argument(..., help="货币对列表，如BTCUSDT ETHUSDT"),
    interval: str = typer.Argument(..., help="时间周期，如1m, 5m, 1h, 1d"),
    start: Optional[str] = typer.Option(None, "--start", "-s", help="开始时间"),
    end: Optional[str] = typer.Option(None, "--end", "-e", help="结束时间"),
    market_type: str = typer.Option("crypto", "--market", "-m", help="市场类型"),
    crypto_type: str = typer.Option("spot", "--crypto-type", "-c", help="加密货币类型"),
):
    """
    批量检查多个货币对的K线数据健康状态
    
    示例:
        python check_kline_health.py batch-check BTCUSDT ETHUSDT BNBUSDT 1h
    """
    import json
    
    # 解析时间参数
    start_dt = None
    end_dt = None
    
    if start:
        try:
            start_dt = datetime.fromisoformat(start)
        except ValueError:
            try:
                start_dt = datetime.strptime(start, "%Y-%m-%d")
            except ValueError:
                logger.error(f"无效的开始时间格式: {start}")
                raise typer.Exit(1)
    
    if end:
        try:
            end_dt = datetime.fromisoformat(end)
        except ValueError:
            try:
                end_dt = datetime.strptime(end, "%Y-%m-%d")
            except ValueError:
                logger.error(f"无效的结束时间格式: {end}")
                raise typer.Exit(1)
    
    checker = KlineHealthChecker()
    results = {}
    has_failures = False
    
    for symbol in symbols:
        logger.info(f"正在检查 {symbol}...")
        result = checker.check_all(symbol, interval, start_dt, end_dt, market_type, crypto_type)
        results[symbol] = result
        if result["overall_status"] == "fail":
            has_failures = True
    
    # 输出汇总结果
    summary = {
        "total_checked": len(symbols),
        "passed": sum(1 for r in results.values() if r["overall_status"] == "pass"),
        "failed": sum(1 for r in results.values() if r["overall_status"] == "fail"),
        "details": results
    }
    
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    
    if has_failures:
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
