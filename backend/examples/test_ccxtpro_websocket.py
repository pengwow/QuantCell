#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CCXT Pro WebSocket测试脚本
用于测试ccxtpro的watch_ohlcv_for_symbols功能

配置说明：
1. 可以通过修改PROXY_ENABLED变量来启用/禁用代理
2. 代理配置在PROXY_CONFIG字典中
3. 可以通过修改SYMBOL_INTERVALS列表来调整订阅的交易对和时间周期
4. 可以通过修改EXCHANGE_NAME变量来切换交易所

使用方法：
python test_ccxtpro_websocket.py
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

# 配置选项
EXCHANGE_NAME = 'binance'  # 交易所名称，如：binance, okx, bybit等
PROXY_ENABLED = False  # 是否启用代理
PROXY_CONFIG = {
    'url': 'socks5://127.0.0.1:7897',
    'username': None,
    'password': None
}

# 订阅列表：[(symbol, interval), ...]
SYMBOL_INTERVALS = [
    ('BTC/USDT', '1d'),
    ('LTC/USDT', '5m'),
    ('ETH/USDT', '1h')
]

# 超时配置（秒）
TIMEOUT_CONFIG = {
    'timeout': 30,  # 总超时时间
    'connectionTimeout': 15,  # 连接超时时间
    'recvTimeout': 20,  # 接收超时时间
    'sendTimeout': 10  # 发送超时时间
}

async def test_ccxtpro_websocket():
    """测试ccxtpro的websocket功能"""
    logger.info(f"开始测试CCXT Pro WebSocket功能")
    logger.info(f"交易所: {EXCHANGE_NAME}")
    
    # 交易所配置
    exchange_config = {
        'enableRateLimit': True,
        'timeout': TIMEOUT_CONFIG['timeout'],
        'options': {
            'defaultType': 'spot',
            'adjustForTimeDifference': True,
            # 只加载现货市场，避免访问期货API
            'watchOHLCVForSymbols': True,
        }
    }
    
    # 配置代理
    if PROXY_ENABLED:
        proxy_url = PROXY_CONFIG['url']
        exchange_config['proxy'] = proxy_url
        logger.info(f"使用代理: {proxy_url}")
    else:
        logger.info("不使用代理，直接连接")
    
    # 初始化交易所客户端
    try:
        exchange_class = getattr(ccxtpro, EXCHANGE_NAME.lower())
        exchange = exchange_class(exchange_config)
    except Exception as e:
        logger.error(f"初始化交易所客户端失败: {e}")
        logger.exception(e)
        return
    
    # 优先使用更简单的watch_ohlcv方法，避免加载过多市场数据
    if hasattr(exchange, 'watch_ohlcv'):
        logger.info(f"交易所 {exchange.id} 支持 watch_ohlcv 方法，将使用该方法进行测试")
        
        try:
            # 连接并获取K线数据
            logger.info(f"开始订阅K线数据: {SYMBOL_INTERVALS}")
            
            # 为每个交易对创建一个独立的任务
            tasks = []
            for symbol, interval in SYMBOL_INTERVALS:
                async def watch_single_symbol(s, i):
                    while True:
                        try:
                            logger.info(f"开始订阅 {s} {i} K线数据...")
                            candles = await exchange.watch_ohlcv(s, i)
                            timestamp = exchange.iso8601(exchange.milliseconds())
                            logger.info(f"[{timestamp}] {s} {i}: {candles}")
                            print(f"[{timestamp}] {s} {i}: {candles}")
                        except Exception as e:
                            logger.error(f"{s} {i} 接收K线数据异常: {e}")
                            print(f"{s} {i} 接收K线数据异常: {e}")
                            await asyncio.sleep(5)
                            continue
                
                task = asyncio.create_task(watch_single_symbol(symbol, interval))
                tasks.append(task)
            
            # 等待所有任务完成
            await asyncio.gather(*tasks, return_exceptions=True)
            
        except KeyboardInterrupt:
            logger.info("程序被用户中断")
        except Exception as e:
            logger.error(f"订阅K线数据失败: {e}")
            logger.exception(e)
    
    # 如果watch_ohlcv方法不可用，再尝试使用watch_ohlcv_for_symbols方法
    elif hasattr(exchange, 'watch_ohlcv_for_symbols'):
        logger.info(f"交易所 {exchange.id} 支持 watch_ohlcv_for_symbols 方法，将使用该方法进行测试")
        
        # 订阅参数
        since = None
        limit = None
        params = {}
        
        # 构建订阅列表，格式：[[(symbol, interval), ...]]
        subscriptions = [SYMBOL_INTERVALS]
        
        try:
            # 连接并获取K线数据
            logger.info(f"开始订阅K线数据: {SYMBOL_INTERVALS}")
            
            # 循环接收数据
            while True:
                try:
                    # 等待接收K线数据
                    candles = await exchange.watch_ohlcv_for_symbols(subscriptions, since, limit, params)
                    
                    # 记录接收到的数据
                    timestamp = exchange.iso8601(exchange.milliseconds())
                    logger.info(f"[{timestamp}] 接收到K线数据: {candles}")
                    print(f"[{timestamp}] 接收到K线数据: {candles}")
                    
                except Exception as e:
                    # 记录异常
                    logger.error(f"接收K线数据异常: {e}")
                    print(f"接收K线数据异常: {e}")
                    
                    # 短暂等待后重试
                    await asyncio.sleep(5)
                    continue
        
        except KeyboardInterrupt:
            logger.info("程序被用户中断")
        except Exception as e:
            logger.error(f"订阅K线数据失败: {e}")
            logger.exception(e)
    
    else:
        logger.error(f"交易所 {exchange.id} 不支持 watch_ohlcv 和 watch_ohlcv_for_symbols 方法")
        await exchange.close()
        return
    
    # 确保在所有情况下都能正确关闭交易所连接
    await exchange.close()
    logger.info("已关闭交易所连接")

async def main():
    """主函数"""
    await test_ccxtpro_websocket()

if __name__ == "__main__":
    # 运行测试
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("程序被用户中断")
    except Exception as e:
        logger.error(f"程序运行异常: {e}")
        logger.exception(e)
