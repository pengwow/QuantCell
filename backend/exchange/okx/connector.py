import asyncio
import aiohttp
import time
import hmac
import hashlib
from typing import Dict, List, Optional, Any, Callable
from datetime import datetime, timedelta
import urllib.parse
import json
import ccxt
from .. import Exchange
from typing import Dict, List, Optional, Any


class OkxExchange(Exchange):
    """Okx交易所连接器实现"""


    def __init__(self, exchange_name: str = 'okx', api_key: Optional[str] = None, 
                 secret_key: Optional[str] = None, trading_mode: str = 'spot', 
                 proxy_url: Optional[str] = None, testnet: bool = False, api_passphrase: Optional[str] = None):
        """
        初始化OKX交易所实例

        :param exchange_name: 交易所名称
        :param api_key: OKX API密钥
        :param secret_key: OKX API密钥密钥
        :param trading_mode: 交易模式，默认为spot
        :param proxy_url: 代理URL
        :param testnet: 是否为模拟交易环境（True为模拟盘，False为实盘）
        :param api_passphrase: OKX API密码
        """
        super().__init__(exchange_name, api_key, secret_key, trading_mode, proxy_url, testnet, api_passphrase)
        
        # 初始化CCXT交易所实例
        self.exchange = ccxt.okx({
            'apiKey': api_key,
            'secret': secret_key,
            'password': api_passphrase,
            'enableRateLimit': True,
            'options': {'defaultType': trading_mode},
        })
        
        # 配置代理
        if proxy_url:
            self.exchange.proxies = {
                'https': proxy_url,
                'http': proxy_url
            }
        
        # 配置测试网络
        if testnet:
            self.exchange.set_sandbox_mode(True)
        
        self.trading_mode = trading_mode
        self.exchange.load_markets()
        self._symbols = None
        
        # 定义K线数据的字段名称
        self.candle_names = [
            'open_time', 'open', 'high', 'low', 'close', 'volume',
            'close_time', 'quote_volume', 'count', 'taker_buy_volume',
            'taker_buy_quote_volume', 'ignore'
        ]
        
        self.api_passphrase = api_passphrase

    @staticmethod
    def format_candle(candle: list) -> dict:
        """
        静态方法，用于将 K 线数据列表格式化为字典
        :param candle: K 线数据列表
        :return: 格式化后的 K 线数据字典
        """
        return dict(
            open_time=candle[0],
            open=candle[1],
            high=candle[2],
            low=candle[3],
            close=candle[4],
            volume=candle[5],
            close_time=candle[6],
            quote_volume=candle[7],
            count=candle[8],
            taker_buy_volume=candle[9],
            taker_buy_quote_volume=candle[10],
            ignore=candle[11]
        )

    def download_data(self, symbol: str, interval: str, start_time: Optional[int] = None, 
                     end_time: Optional[int] = None, limit: int = 500, 
                     candle_type: Optional[str] = None, progress_queue: Optional[Any] = None) -> List[Dict[str, Any]]:
        """
        下载 K 线数据
        
        Args:
            symbol: 交易对符号
            interval: 时间间隔，如 '1m', '1h' 等
            start_time: 开始时间戳（毫秒）
            end_time: 结束时间戳（毫秒）
            limit: 每次获取数据的最大条数，默认为 500
            candle_type: 交易模式，spot 或 future，默认为 None
            progress_queue: 进度队列
            
        Returns:
            K 线数据列表
        """
        try:
            # 使用 CCXT 的 fetch_ohlcv 方法获取 K 线数据
            ohlcv_data = self.exchange.fetch_ohlcv(
                symbol=symbol,
                timeframe=interval,
                since=start_time,
                limit=limit
            )
            
            # 格式化 K 线数据
            formatted_data = [self.format_candle(candle) for candle in ohlcv_data]
            return formatted_data
        except Exception as e:
            print(f"下载 K 线数据失败: {e}")
            return []

    def load_data(self, symbol: str, interval: str, start_time: Optional[int] = None, 
                 end_time: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        加载 K 线数据
        
        Args:
            symbol: 交易对符号
            interval: 时间间隔，如 '1m', '1h' 等
            start_time: 开始时间戳（毫秒）
            end_time: 结束时间戳（毫秒）
            
        Returns:
            K 线数据列表
        """
        # 直接调用 download_data 方法获取数据
        return self.download_data(symbol, interval, start_time, end_time)

    def health_check(self) -> bool:
        """
        策略健康检查，确保市场数据和账户信息正常
        
        :return: True表示健康状态良好，False表示存在异常需要处理
        """
        try:
            # 简单的健康检查：尝试获取交易所状态
            self.exchange.ping()
            return True
        except Exception as e:
            print(f"健康检查失败: {e}")
            return False

    def check_status(self) -> bool:
        """
        检查交易所系统状态，避免在维护期间进行交易
        
        :return: True表示交易所正常，False表示存在维护或异常
        """
        try:
            # 使用CCXT的fetch_status方法检查交易所状态
            status = self.exchange.fetch_status()
            return status.get('status', 'unknown') == 'ok'
        except Exception:
            # 如果fetch_status不可用，退回到ping检查
            return self.health_check()

    @property
    def symbols(self) -> List[str]:
        """
        获取交易所支持的所有交易对
        
        Returns:
            交易对列表
        """
        if not self._symbols:
            self._symbols = [symbol for symbol in self.exchange.symbols if ':' not in symbol]
        return self._symbols

    def get_balance(self) -> Dict[str, Any]:
        """
        获取账户余额
        
        Returns:
            账户余额信息
        """
        try:
            return self.exchange.fetch_balance()
        except Exception as e:
            print(f"获取账户余额失败: {e}")
            return {}

    def set_account_config(self) -> None:
        """
        设置账户配置
        
        账户模式决定了：
        1. 可用的交易类型（现货/保证金/衍生品）
        2. 保证金计算方式
        3. 风险控制规则
        4. 资金利用率
        """
        # OKX账户配置逻辑简化实现
        print("账户配置设置方法")


if __name__ == "__main__":
    """测试OKX交易所基本功能"""
    # 简单测试
    client = OkxExchange()
    print(f"支持的交易对数量: {len(client.symbols)}")
    print(f"前5个交易对: {client.symbols[:5]}")
    print(f"健康检查: {'通过' if client.health_check() else '失败'}")
    print(f"交易所状态: {'正常' if client.check_status() else '异常'}")
    
    # 测试获取K线数据
    # btc_1m = client.download_data('BTC/USDT', '1m', limit=10)
    # print(f"BTC/USDT 1m K线数据条数: {len(btc_1m)}")
    # if btc_1m:
    #     print(f"最新K线数据: {btc_1m[-1]}")
