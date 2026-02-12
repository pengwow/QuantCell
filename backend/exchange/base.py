"""
交易所基础模块

提供交易所抽象基类和加密货币数据收集器基类。

主要类:
    - BaseExchange: 交易所抽象基类
    - CryptoBaseCollector: 加密货币数据收集器基类

作者: QuantCell Team
版本: 1.0.0
日期: 2026-02-12
"""

import abc
from abc import ABC, abstractmethod
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import pandas as pd
from loguru import logger

from exchange.types import (
    ExchangeFeatures,
    Order,
    OrderSide,
    OrderType,
    OrderStatus,
    Balance,
    Ticker,
    OHLCV,
    OrderBook,
    Trade,
    AccountInfo,
    Position,
    FundingRate,
    StakingProduct,
    SubAccount,
    TradingMode,
    MarginMode,
)
from exchange.exceptions import (
    ConnectionError,
    NotImplementedFeatureError,
    ExchangeError,
)
from exchange.decorators import require_connected, require_feature
from common.collectors import BaseCollector


class BaseExchange(ABC):
    """
    交易所抽象基类
    
    定义所有交易所的通用接口和功能。
    
    Attributes:
        exchange_name: 交易所名称
        api_key: API密钥
        secret_key: API密钥密钥
        trading_mode: 交易模式
        proxy_url: 代理URL
        testnet: 是否使用测试网络
        _exchange_features: 功能特性字典
    """

    _exchange_features: ExchangeFeatures = {
        "spot_trading": True,
        "margin_trading": False,
        "futures_trading": False,
        "stoploss_on_exchange": False,
        "stoploss_order_types": {},
        "stoploss_blocks_assets": True,
        "order_time_in_force": ["GTC"],
        "ohlcv_candle_limit": 1000,
        "ohlcv_has_history": True,
        "ohlcv_partial_candle": True,
        "tickers_have_bid_ask": True,
        "tickers_have_price": True,
        "tickers_have_quote_volume": True,
        "tickers_have_percentage": True,
        "fetch_my_trades": True,
        "fetch_trades": True,
        "trades_pagination": "time",
        "trades_pagination_arg": "since",
        "trades_has_history": False,
        "l2_limit_range": [5, 10, 20, 50, 100, 500, 1000],
        "l2_limit_range_required": False,
        "sub_account": False,
        "staking": False,
        "savings": False,
        "convert": False,
        "margin_loan": False,
        "futures_leverage": False,
        "funding_rate": False,
        "ws_enabled": False,
    }

    def __init__(
        self,
        exchange_name: str,
        api_key: Optional[str] = None,
        secret_key: Optional[str] = None,
        trading_mode: str = "spot",
        proxy_url: Optional[str] = None,
        testnet: bool = False,
        **kwargs
    ):
        """
        初始化交易所连接器
        
        Args:
            exchange_name: 交易所名称
            api_key: API密钥
            secret_key: API密钥密钥
            trading_mode: 交易模式，如 'spot', 'margin', 'futures'
            proxy_url: 代理URL
            testnet: 是否使用测试网络
            **kwargs: 其他配置参数
        """
        self.exchange_name = exchange_name
        self.api_key = api_key
        self.secret_key = secret_key
        self.trading_mode = trading_mode
        self.proxy_url = proxy_url
        self.testnet = testnet
        self._connected = False
        self._config = kwargs
        self._symbols: Optional[List[str]] = None
        
        logger.info(f"{self.__class__.__name__} initialized (testnet={testnet})")

    @property
    def is_connected(self) -> bool:
        """检查是否已连接"""
        return self._connected

    def _ensure_connected(self):
        """确保已连接，否则抛出异常"""
        if not self._connected:
            raise ConnectionError(
                f"Exchange {self.exchange_name} is not connected. Call connect() first.",
                exchange_name=self.exchange_name,
            )

    @abstractmethod
    def connect(self) -> bool:
        """
        建立与交易所的连接
        
        Returns:
            bool: 连接是否成功
            
        Raises:
            ConnectionError: 连接失败时
            AuthenticationError: 认证失败时
        """
        pass

    @abstractmethod
    def disconnect(self) -> None:
        """断开与交易所的连接"""
        pass

    @abstractmethod
    def health_check(self) -> bool:
        """
        健康检查
        
        Returns:
            bool: True表示健康，False表示异常
        """
        pass

    def check_status(self) -> bool:
        """
        检查交易所系统状态
        
        Returns:
            bool: True表示正常，False表示维护或异常
        """
        try:
            return self.health_check()
        except Exception:
            return False

    @abstractmethod
    def get_ticker(self, symbol: str) -> Ticker:
        """
        获取最新行情
        
        Args:
            symbol: 交易对，如 "BTCUSDT"
            
        Returns:
            Ticker: 行情数据
        """
        pass

    @abstractmethod
    def get_ohlcv(
        self,
        symbol: str,
        timeframe: str,
        limit: int = 500,
        since: Optional[int] = None,
    ) -> List[OHLCV]:
        """
        获取K线数据
        
        Args:
            symbol: 交易对
            timeframe: 时间间隔，如 "1m", "5m", "1h", "1d"
            limit: 返回条数
            since: 开始时间（毫秒时间戳）
            
        Returns:
            List[OHLCV]: K线数据列表
        """
        pass

    @abstractmethod
    def get_order_book(self, symbol: str, limit: int = 100) -> OrderBook:
        """
        获取订单簿（深度）
        
        Args:
            symbol: 交易对
            limit: 深度条数
            
        Returns:
            OrderBook: 订单簿数据
        """
        pass

    @abstractmethod
    def get_recent_trades(self, symbol: str, limit: int = 100) -> List[Trade]:
        """
        获取最近成交记录
        
        Args:
            symbol: 交易对
            limit: 返回条数
            
        Returns:
            List[Trade]: 成交记录列表
        """
        pass

    @abstractmethod
    def get_balance(self, asset: Optional[str] = None) -> List[Balance]:
        """
        获取账户余额
        
        Args:
            asset: 指定资产，如果为None则返回所有资产余额
            
        Returns:
            List[Balance]: 余额列表
        """
        pass

    @abstractmethod
    def get_account_info(self) -> AccountInfo:
        """
        获取账户信息
        
        Returns:
            AccountInfo: 账户信息
        """
        pass

    @abstractmethod
    def create_order(self, order: Order) -> Order:
        """
        创建订单
        
        Args:
            order: 订单对象
            
        Returns:
            Order: 创建后的订单（包含订单ID）
        """
        pass

    @abstractmethod
    def cancel_order(self, symbol: str, order_id: str) -> bool:
        """
        取消订单
        
        Args:
            symbol: 交易对
            order_id: 订单ID
            
        Returns:
            bool: 是否成功取消
        """
        pass

    @abstractmethod
    def get_order(self, symbol: str, order_id: str) -> Order:
        """
        查询订单状态
        
        Args:
            symbol: 交易对
            order_id: 订单ID
            
        Returns:
            Order: 订单信息
        """
        pass

    @abstractmethod
    def get_open_orders(self, symbol: Optional[str] = None) -> List[Order]:
        """
        获取当前挂单
        
        Args:
            symbol: 交易对，如果为None则返回所有挂单
            
        Returns:
            List[Order]: 挂单列表
        """
        pass

    @abstractmethod
    def get_order_history(
        self,
        symbol: Optional[str] = None,
        limit: int = 500,
    ) -> List[Order]:
        """
        获取历史订单
        
        Args:
            symbol: 交易对
            limit: 返回条数
            
        Returns:
            List[Order]: 历史订单列表
        """
        pass

    @abstractmethod
    def get_my_trades(
        self,
        symbol: Optional[str] = None,
        limit: int = 500,
    ) -> List[Trade]:
        """
        获取成交记录
        
        Args:
            symbol: 交易对
            limit: 返回条数
            
        Returns:
            List[Trade]: 成交记录列表
        """
        pass

    def get_sub_accounts(self) -> List[SubAccount]:
        """
        获取子账户列表
        
        Returns:
            List[SubAccount]: 子账户列表
            
        Raises:
            NotImplementedFeatureError: 交易所不支持子账户功能
        """
        raise NotImplementedFeatureError(
            f"Sub-account is not supported by {self.exchange_name}",
            exchange_name=self.exchange_name,
            feature="sub_account",
        )

    def create_sub_account(self, email: str) -> SubAccount:
        """
        创建子账户
        
        Args:
            email: 子账户邮箱
            
        Returns:
            SubAccount: 创建的子账户
            
        Raises:
            NotImplementedFeatureError: 交易所不支持子账户功能
        """
        raise NotImplementedFeatureError(
            f"Sub-account is not supported by {self.exchange_name}",
            exchange_name=self.exchange_name,
            feature="sub_account",
        )

    def get_staking_products(self, product: str = "STAKING") -> List[StakingProduct]:
        """
        获取质押产品列表
        
        Args:
            product: 产品类型，如 "STAKING", "F_DEFI", "L_DEFI"
            
        Returns:
            List[StakingProduct]: 质押产品列表
            
        Raises:
            NotImplementedFeatureError: 交易所不支持质押功能
        """
        raise NotImplementedFeatureError(
            f"Staking is not supported by {self.exchange_name}",
            exchange_name=self.exchange_name,
            feature="staking",
        )

    def purchase_staking(
        self,
        product: str,
        product_id: str,
        amount: Decimal,
    ) -> Dict[str, Any]:
        """
        购买质押产品
        
        Args:
            product: 产品类型
            product_id: 产品ID
            amount: 购买金额
            
        Returns:
            Dict: 购买结果
            
        Raises:
            NotImplementedFeatureError: 交易所不支持质押功能
        """
        raise NotImplementedFeatureError(
            f"Staking is not supported by {self.exchange_name}",
            exchange_name=self.exchange_name,
            feature="staking",
        )

    def convert_request(
        self,
        from_asset: str,
        to_asset: str,
        amount: Decimal,
    ) -> Dict[str, Any]:
        """
        请求闪兑
        
        Args:
            from_asset: 源资产
            to_asset: 目标资产
            amount: 兑换金额
            
        Returns:
            Dict: 闪兑请求结果
            
        Raises:
            NotImplementedFeatureError: 交易所不支持闪兑功能
        """
        raise NotImplementedFeatureError(
            f"Convert is not supported by {self.exchange_name}",
            exchange_name=self.exchange_name,
            feature="convert",
        )

    def margin_borrow(
        self,
        asset: str,
        amount: Decimal,
        is_isolated: bool = False,
        symbol: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        杠杆借币
        
        Args:
            asset: 借币资产
            amount: 借币数量
            is_isolated: 是否是逐仓
            symbol: 交易对（逐仓时需要）
            
        Returns:
            Dict: 借币结果
            
        Raises:
            NotImplementedFeatureError: 交易所不支持杠杆功能
        """
        raise NotImplementedFeatureError(
            f"Margin trading is not supported by {self.exchange_name}",
            exchange_name=self.exchange_name,
            feature="margin_loan",
        )

    def margin_repay(
        self,
        asset: str,
        amount: Decimal,
        is_isolated: bool = False,
        symbol: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        杠杆还币
        
        Args:
            asset: 还币资产
            amount: 还币数量
            is_isolated: 是否是逐仓
            symbol: 交易对（逐仓时需要）
            
        Returns:
            Dict: 还币结果
            
        Raises:
            NotImplementedFeatureError: 交易所不支持杠杆功能
        """
        raise NotImplementedFeatureError(
            f"Margin trading is not supported by {self.exchange_name}",
            exchange_name=self.exchange_name,
            feature="margin_loan",
        )

    def set_leverage(self, symbol: str, leverage: int) -> Dict[str, Any]:
        """
        设置杠杆倍数
        
        Args:
            symbol: 交易对
            leverage: 杠杆倍数
            
        Returns:
            Dict: 设置结果
            
        Raises:
            NotImplementedFeatureError: 交易所不支持合约功能
        """
        raise NotImplementedFeatureError(
            f"Futures trading is not supported by {self.exchange_name}",
            exchange_name=self.exchange_name,
            feature="futures_leverage",
        )

    def get_funding_rate(self, symbol: str) -> FundingRate:
        """
        获取资金费率
        
        Args:
            symbol: 交易对
            
        Returns:
            FundingRate: 资金费率信息
            
        Raises:
            NotImplementedFeatureError: 交易所不支持合约功能
        """
        raise NotImplementedFeatureError(
            f"Futures trading is not supported by {self.exchange_name}",
            exchange_name=self.exchange_name,
            feature="funding_rate",
        )

    def get_position(self, symbol: str) -> Position:
        """
        获取持仓
        
        Args:
            symbol: 交易对
            
        Returns:
            Position: 持仓信息
            
        Raises:
            NotImplementedFeatureError: 交易所不支持合约功能
        """
        raise NotImplementedFeatureError(
            f"Futures trading is not supported by {self.exchange_name}",
            exchange_name=self.exchange_name,
            feature="futures_leverage",
        )

    def get_positions(self) -> List[Position]:
        """
        获取所有持仓
        
        Returns:
            List[Position]: 持仓列表
            
        Raises:
            NotImplementedFeatureError: 交易所不支持合约功能
        """
        raise NotImplementedFeatureError(
            f"Futures trading is not supported by {self.exchange_name}",
            exchange_name=self.exchange_name,
            feature="futures_leverage",
        )


class CryptoBaseCollector(BaseCollector):
    """
    加密货币基础收集器类
    
    定义加密货币数据收集的通用接口和功能。
    
    Attributes:
        candle_names: K线数据列名列表
    """
    
    def __init__(
        self,
        save_dir: Union[str, Path],
        start=None,
        end=None,
        interval="1d",
        max_workers=1,
        max_collector_count=2,
        delay=0,
        check_data_length: Optional[int] = None,
        limit_nums: Optional[int] = None,
        mode='inc',
    ):
        """
        初始化加密货币收集器
        
        :param save_dir: 数据保存目录
        :param start: 开始时间
        :param end: 结束时间
        :param interval: 时间间隔，如'1m', '1h', '1d'等
        :param max_workers: 最大工作线程数
        :param max_collector_count: 最大收集次数
        :param delay: 请求延迟时间（秒）
        :param check_data_length: 数据长度检查阈值
        :param limit_nums: 限制收集的标的数量，用于调试
        :param mode: 下载模式，可选'inc'（增量）或'full'（全量），默认'inc'
        """
        super().__init__(
            save_dir=save_dir,
            start=start,
            end=end,
            interval=interval,
            max_workers=max_workers,
            max_collector_count=max_collector_count,
            delay=delay,
            check_data_length=check_data_length,
            limit_nums=limit_nums,
            mode=mode,
        )
        
        self.candle_names = [
            'open_time', 'open', 'high', 'low', 'close', 'volume',
            'close_time', 'quote_volume', 'count', 'taker_buy_volume',
            'taker_buy_quote_volume', 'ignore'
        ]
    
    @property
    @abc.abstractmethod
    def _timezone(self):
        """获取时区"""
        raise NotImplementedError("请重写_timezone属性")
    
    @staticmethod
    def format_candle(candle: list) -> dict:
        """
        格式化K线数据
        
        :param candle: K线数据列表
        :return: 格式化后的K线数据字典
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
    
    def normalize_symbol(self, symbol):
        """
        标准化加密货币符号，去除'/'分隔符
        
        :param symbol: 加密货币符号，如'BTC/USDT'
        :return: 标准化后的符号，如'BTCUSDT'
        """
        return symbol.replace('/', '')
    
    def get_instrument_list(self):
        """
        获取加密货币标的列表
        
        :return: 加密货币标的列表
        """
        logger.warning("get_instrument_list方法未被重写，返回空列表")
        return []


__all__ = ["BaseExchange", "CryptoBaseCollector"]
