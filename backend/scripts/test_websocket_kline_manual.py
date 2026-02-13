#!/usr/bin/env python3
"""
WebSocket K线数据手动测试脚本

用于模拟前端图表页面接收并处理实时K线数据
功能包括：
- 建立与Binance的WebSocket连接
- 接收实时推送的K线数据
- 模拟前端图表页面的数据处理流程
- 完整输出接收到的K线数据
- 连接状态监控、异常处理和数据接收日志记录

使用方法:
    cd /Users/liupeng/workspace/quant/QuantCell/backend
    python scripts/test_websocket_kline_manual.py --symbols BTCUSDT,ETHUSDT --intervals 1m,5m --duration 60

参数说明:
    --symbols: 交易对列表，逗号分隔 (默认: BTCUSDT,ETHUSDT)
    --intervals: K线周期列表，逗号分隔 (默认: 1m,5m)
    --duration: 测试持续时间（秒）(默认: 60)
    --testnet: 使用测试网络 (默认: True)
    --verbose: 详细日志输出 (默认: False)
"""

import asyncio
import sys
import time
import signal
from datetime import datetime
from typing import Dict, List, Any, Optional
from collections import defaultdict

import typer
from typing_extensions import Annotated

# 添加项目根目录到Python路径
sys.path.insert(0, '/Users/liupeng/workspace/quant/QuantCell/backend')

from loguru import logger
from exchange.binance.websocket_client import BinanceWebSocketClient
from exchange.binance.config import BinanceConfig


# 配置日志
logger.remove()
logger.add(
    sys.stdout,
    format="<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
    level="INFO",
    colorize=True
)


class KlineDataTester:
    """K线数据测试器"""
    
    def __init__(self, symbols: List[str], intervals: List[str], duration: int = 60, testnet: bool = True):
        """
        初始化测试器
        
        Args:
            symbols: 交易对列表，如 ['BTCUSDT', 'ETHUSDT']
            intervals: K线周期列表，如 ['1m', '5m']
            duration: 测试持续时间（秒）
            testnet: 是否使用测试网络
        """
        self.symbols = symbols
        self.intervals = intervals
        self.duration = duration
        self.testnet = testnet
        
        # 构建频道列表
        self.channels = []
        for symbol in symbols:
            for interval in intervals:
                self.channels.append(f"{symbol}@kline_{interval}")
        
        # 客户端实例
        self.client: Optional[BinanceWebSocketClient] = None
        
        # 统计数据
        self.stats = {
            'start_time': None,
            'end_time': None,
            'total_messages': 0,
            'messages_by_channel': defaultdict(int),
            'messages_by_symbol': defaultdict(int),
            'first_message_time': None,
            'last_message_time': None,
            'errors': [],
            'reconnects': 0,
        }
        
        # 最新K线数据缓存
        self.latest_klines: Dict[str, Dict[str, Any]] = {}
        
        # 运行状态
        self.running = False
        self._stop_event = asyncio.Event()
        
        logger.info(f"KlineDataTester initialized")
        logger.info(f"  Symbols: {symbols}")
        logger.info(f"  Intervals: {intervals}")
        logger.info(f"  Channels: {self.channels}")
        logger.info(f"  Duration: {duration}s")
        logger.info(f"  Testnet: {testnet}")
    
    def _on_message(self, data: Dict[str, Any]):
        """
        处理接收到的消息
        
        Args:
            data: 消息数据
        """
        try:
            self.stats['total_messages'] += 1
            
            # 记录时间
            current_time = time.time()
            if self.stats['first_message_time'] is None:
                self.stats['first_message_time'] = current_time
            self.stats['last_message_time'] = current_time
            
            # 获取频道信息
            channel = data.get('channel', 'unknown')
            self.stats['messages_by_channel'][channel] += 1
            
            # 解析K线数据
            if 'k' in data:
                kline = data['k']
                symbol = kline.get('s', 'unknown')
                interval = kline.get('i', 'unknown')
                
                self.stats['messages_by_symbol'][f"{symbol}@{interval}"] += 1
                
                # 缓存最新K线
                key = f"{symbol}@{interval}"
                self.latest_klines[key] = {
                    'symbol': symbol,
                    'interval': interval,
                    'open_time': kline.get('t'),
                    'close_time': kline.get('T'),
                    'open': float(kline.get('o', 0)),
                    'high': float(kline.get('h', 0)),
                    'low': float(kline.get('l', 0)),
                    'close': float(kline.get('c', 0)),
                    'volume': float(kline.get('v', 0)),
                    'quote_volume': float(kline.get('q', 0)),
                    'trades': kline.get('n', 0),
                    'is_final': kline.get('x', False),
                    'receive_time': datetime.now().isoformat(),
                }
                
                # 输出K线数据
                self._print_kline(self.latest_klines[key], channel)
            
        except Exception as e:
            logger.error(f"Error processing message: {e}")
            self.stats['errors'].append({
                'time': datetime.now().isoformat(),
                'error': str(e),
                'data': data,
            })
    
    def _print_kline(self, kline: Dict[str, Any], channel: str):
        """
        打印K线数据（详细输出所有字段）
        
        Args:
            kline: K线数据
            channel: 频道名称
        """
        is_final = "✓" if kline['is_final'] else "○"
        
        # 将时间戳转换为可读格式
        open_time_str = datetime.fromtimestamp(kline['open_time'] / 1000).strftime('%Y-%m-%d %H:%M:%S') if kline['open_time'] else 'N/A'
        close_time_str = datetime.fromtimestamp(kline['close_time'] / 1000).strftime('%Y-%m-%d %H:%M:%S') if kline['close_time'] else 'N/A'
        
        logger.info("=" * 80)
        logger.info(f"[{channel}] {is_final} Kline Data:")
        logger.info("-" * 80)
        
        # 基本信息
        logger.info(f"  Symbol:        {kline['symbol']}")
        logger.info(f"  Interval:      {kline['interval']}")
        logger.info(f"  Is Final:      {kline['is_final']}")
        
        # 时间信息
        logger.info(f"  Open Time:     {open_time_str} ({kline['open_time']})")
        logger.info(f"  Close Time:    {close_time_str} ({kline['close_time']})")
        
        # 价格信息
        logger.info(f"  Open:          {kline['open']:.8f}")
        logger.info(f"  High:          {kline['high']:.8f}")
        logger.info(f"  Low:           {kline['low']:.8f}")
        logger.info(f"  Close:         {kline['close']:.8f}")
        
        # 成交量信息
        logger.info(f"  Volume:        {kline['volume']:.8f}")
        logger.info(f"  Quote Volume:  {kline['quote_volume']:.8f}")
        
        # 交易信息
        logger.info(f"  Trades:        {kline['trades']}")
        
        # 接收时间
        logger.info(f"  Receive Time:  {kline['receive_time']}")
        
        logger.info("=" * 80)
    
    async def connect(self) -> bool:
        """
        建立WebSocket连接
        
        Returns:
            bool: 连接是否成功
        """
        try:
            logger.info("Connecting to Binance WebSocket...")
            
            # 创建配置
            config = BinanceConfig(
                api_key="",
                api_secret="",
                testnet=self.testnet,
            )
            
            # 创建客户端
            self.client = BinanceWebSocketClient(config)
            
            # 添加消息回调
            self.client.add_message_callback(self._on_message)
            
            # 建立连接
            success = await self.client.connect()
            
            if success:
                logger.info("✓ WebSocket connected successfully")
                self.stats['start_time'] = time.time()
                return True
            else:
                logger.error("✗ Failed to connect WebSocket")
                return False
                
        except Exception as e:
            logger.error(f"Error connecting: {e}")
            return False
    
    async def subscribe(self) -> bool:
        """
        订阅K线频道
        
        Returns:
            bool: 订阅是否成功
        """
        try:
            logger.info(f"Subscribing to {len(self.channels)} channels...")
            
            success = await self.client.subscribe(self.channels)
            
            if success:
                logger.info(f"✓ Subscribed to channels: {self.channels}")
                return True
            else:
                logger.error("✗ Failed to subscribe to channels")
                return False
                
        except Exception as e:
            logger.error(f"Error subscribing: {e}")
            return False
    
    async def run(self):
        """
        运行测试
        """
        logger.info("=" * 80)
        logger.info("Starting WebSocket Kline Data Test")
        logger.info("=" * 80)
        
        # 建立连接
        if not await self.connect():
            return False
        
        # 订阅频道
        if not await self.subscribe():
            await self.disconnect()
            return False
        
        # 设置运行状态
        self.running = True
        
        # 设置信号处理
        def signal_handler(sig, frame):
            logger.info("\nReceived stop signal, shutting down...")
            self._stop_event.set()
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        
        logger.info(f"Test running for {self.duration} seconds...")
        logger.info("Press Ctrl+C to stop early")
        logger.info("-" * 80)
        
        try:
            # 等待测试时间或停止信号
            await asyncio.wait_for(
                self._stop_event.wait(),
                timeout=self.duration
            )
        except asyncio.TimeoutError:
            logger.info("Test duration completed")
        
        # 停止运行
        self.running = False
        self.stats['end_time'] = time.time()
        
        # 断开连接
        await self.disconnect()
        
        # 打印报告
        self._print_report()
        
        return True
    
    async def disconnect(self):
        """
        断开连接
        """
        try:
            if self.client:
                logger.info("Disconnecting...")
                await self.client.disconnect()
                logger.info("✓ Disconnected")
        except Exception as e:
            logger.error(f"Error disconnecting: {e}")
    
    def _print_report(self):
        """
        打印测试报告
        """
        logger.info("=" * 80)
        logger.info("Test Report")
        logger.info("=" * 80)
        
        # 基本信息
        duration = self.stats['end_time'] - self.stats['start_time'] if self.stats['end_time'] else 0
        logger.info(f"Test Duration: {duration:.2f} seconds")
        logger.info(f"Total Messages: {self.stats['total_messages']}")
        
        # 消息频率
        if duration > 0:
            msg_rate = self.stats['total_messages'] / duration
            logger.info(f"Message Rate: {msg_rate:.2f} msg/s")
        
        # 按频道统计
        logger.info("-" * 80)
        logger.info("Messages by Channel:")
        for channel, count in sorted(self.stats['messages_by_channel'].items()):
            logger.info(f"  {channel}: {count}")
        
        # 按交易对统计
        logger.info("-" * 80)
        logger.info("Messages by Symbol:")
        for symbol, count in sorted(self.stats['messages_by_symbol'].items()):
            logger.info(f"  {symbol}: {count}")
        
        # 最新K线数据
        logger.info("-" * 80)
        logger.info("Latest Kline Data:")
        for key, kline in sorted(self.latest_klines.items()):
            logger.info(f"  {key}:")
            logger.info(f"    Open: {kline['open']:.2f}")
            logger.info(f"    High: {kline['high']:.2f}")
            logger.info(f"    Low: {kline['low']:.2f}")
            logger.info(f"    Close: {kline['close']:.2f}")
            logger.info(f"    Volume: {kline['volume']:.4f}")
            logger.info(f"    Is Final: {kline['is_final']}")
        
        # 错误统计
        if self.stats['errors']:
            logger.info("-" * 80)
            logger.info(f"Errors ({len(self.stats['errors'])}):")
            for error in self.stats['errors'][:5]:  # 只显示前5个错误
                logger.info(f"  [{error['time']}] {error['error']}")
            if len(self.stats['errors']) > 5:
                logger.info(f"  ... and {len(self.stats['errors']) - 5} more errors")
        
        logger.info("=" * 80)


# 创建Typer应用
app = typer.Typer(help="WebSocket K线数据手动测试脚本")


@app.command()
def main(
    symbols: Annotated[str, typer.Option(help="交易对列表，逗号分隔", show_default=True)] = "BTCUSDT,ETHUSDT",
    intervals: Annotated[str, typer.Option(help="K线周期列表，逗号分隔", show_default=True)] = "1m,5m",
    duration: Annotated[int, typer.Option(help="测试持续时间（秒）", show_default=True)] = 60,
    testnet: Annotated[bool, typer.Option(help="使用测试网络", show_default=True)] = True,
    verbose: Annotated[bool, typer.Option(help="详细日志输出", show_default=True)] = False,
):
    """
    WebSocket K线数据手动测试脚本
    
    示例:
        # 测试默认交易对和周期（60秒）
        python scripts/test_websocket_kline_manual.py
        
        # 测试指定交易对和周期（120秒）
        python scripts/test_websocket_kline_manual.py --symbols BTCUSDT,ETHUSDT --intervals 1m,5m --duration 120
        
        # 使用生产网络测试
        python scripts/test_websocket_kline_manual.py --testnet False
    """
    # 解析参数
    symbol_list = [s.strip().upper() for s in symbols.split(",")]
    interval_list = [i.strip().lower() for i in intervals.split(",")]
    
    # 设置日志级别
    if verbose:
        logger.remove()
        logger.add(sys.stdout, level="DEBUG")
    
    # 创建测试器
    tester = KlineDataTester(
        symbols=symbol_list,
        intervals=interval_list,
        duration=duration,
        testnet=testnet,
    )
    
    # 运行测试
    success = asyncio.run(tester.run())
    
    # 返回退出码
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    app()
