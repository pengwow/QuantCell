#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CCXT Pro WebSocket测试脚本
用于测试ccxtpro的watch_ohlcv_for_symbols功能，使用socks5代理
"""

import asyncio
import ccxt.pro as ccxtpro
from loguru import logger
import time

# 配置日志
logger.add(
    "ccxt_kline_test.log",
    level="INFO",
    format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}",
    rotation="1 day",
    retention="7 days"
)

async def test_ccxtpro_websocket():
    """测试ccxtpro的websocket功能"""
    # 初始化交易所客户端
    exchange = ccxtpro.binance({
        'enableRateLimit': True,
        'options': {
            'defaultType': 'spot',
        },
    })
    
    # 配置socks5代理
    proxy_url = 'socks5://127.0.0.1:7897'
    exchange.proxy = proxy_url
    
    logger.info(f"使用代理: {proxy_url}")
    logger.info(f"交易所: {exchange.id}")
    
    # 检查交易所是否支持watchOHLCVForSymbols方法
    if not hasattr(exchange, 'watch_ohlcv_for_symbols'):
        logger.error(f"交易所 {exchange.id} 不支持 watch_ohlcv_for_symbols 方法")
        return
    
    logger.info(f"交易所 {exchange.id} 支持 watch_ohlcv_for_symbols 方法")
    
    # 订阅参数
    since = None
    limit = None
    params = {}
    
    # 循环测试
    while True:
        try:
            logger.info("开始订阅K线数据...")
            
            # 订阅列表
            subscriptions = [
                [
                    ['BTC/USDT', '1d'],
                    ['LTC/USDT', '5m'],
                    ['ETH/USDT', '1h']
                ]
            ]
            
            # 等待接收K线数据
            candles = await exchange.watch_ohlcv_for_symbols(subscriptions, since, limit, params)
            
            # 记录接收到的数据
            timestamp = exchange.iso8601(exchange.milliseconds())
            logger.info(f"[{timestamp}] 接收到K线数据: {candles}")
            print(f"[{timestamp}] 接收到K线数据: {candles}")
            
        except Exception as e:
            # 记录异常
            logger.error(f"发生异常: {e}")
            print(f"发生异常: {e}")
            
            # 短暂等待后重试
            await asyncio.sleep(5)
            continue

async def main():
    """主函数"""
    logger.info("开始测试CCXT Pro WebSocket功能")
    await test_ccxtpro_websocket()

if __name__ == "__main__":
    # 运行测试
    asyncio.run(main())
