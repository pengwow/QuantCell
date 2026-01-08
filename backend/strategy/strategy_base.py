# 策略基类
# 定义统一的策略接口，确保所有策略遵循一致的开发规范

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Union
from datetime import datetime
from pydantic import BaseModel, Field
import pandas as pd
import numpy as np


class StrategyParam(BaseModel):
    """
    策略参数模型
    用于定义策略参数的元数据
    """
    name: str = Field(..., description="参数名称")
    type: str = Field(..., description="参数类型")
    default: Any = Field(..., description="默认值")
    description: str = Field(..., description="参数描述")
    min: Optional[float] = Field(None, description="最小值")
    max: Optional[float] = Field(None, description="最大值")
    required: bool = Field(False, description="是否必填")


class StrategyMetadata(BaseModel):
    """
    策略元数据模型
    用于定义策略的基本信息
    """
    name: str = Field(..., description="策略名称")
    description: str = Field(..., description="策略描述")
    version: str = Field("1.0.0", description="策略版本")
    author: Optional[str] = Field(None, description="策略作者")
    created_at: Optional[datetime] = Field(None, description="创建时间")
    updated_at: Optional[datetime] = Field(None, description="更新时间")
    params: List[StrategyParam] = Field(default_factory=list, description="策略参数列表")


class Order(BaseModel):
    """
    订单模型
    用于定义交易订单的基本信息
    """
    symbol: str = Field(..., description="交易标的")
    order_type: str = Field(..., description="订单类型", pattern="^(market|limit|stop|stop_limit)$")
    side: str = Field(..., description="交易方向", pattern="^(buy|sell)$")
    quantity: float = Field(..., description="交易数量")
    price: Optional[float] = Field(None, description="订单价格")
    stop_price: Optional[float] = Field(None, description="止损价格")
    take_profit_price: Optional[float] = Field(None, description="止盈价格")
    timestamp: datetime = Field(default_factory=datetime.now, description="下单时间")
    status: str = Field("pending", description="订单状态", pattern="^(pending|filled|partially_filled|canceled|rejected)$")


class Position(BaseModel):
    """
    持仓模型
    用于定义当前持仓的基本信息
    """
    symbol: str = Field(..., description="交易标的")
    quantity: float = Field(..., description="持仓数量")
    avg_price: float = Field(..., description="平均持仓价格")
    current_price: float = Field(..., description="当前价格")
    unrealized_pnl: float = Field(..., description="未实现盈亏")
    realized_pnl: float = Field(..., description="已实现盈亏")
    timestamp: datetime = Field(default_factory=datetime.now, description="持仓时间")


class StrategySignal(BaseModel):
    """
    策略信号模型
    用于定义策略生成的交易信号
    """
    symbol: str = Field(..., description="交易标的")
    signal_type: str = Field(..., description="信号类型", pattern="^(buy|sell|hold|close)$")
    strength: float = Field(..., description="信号强度", ge=-1.0, le=1.0)
    timestamp: datetime = Field(default_factory=datetime.now, description="信号生成时间")
    params: Dict[str, Any] = Field(default_factory=dict, description="信号参数")


class StrategyBase(ABC):
    """
    策略基类
    定义统一的策略接口，确保所有策略遵循一致的开发规范
    
    策略生命周期：
    1. __init__: 初始化策略实例
    2. initialize: 策略初始化，设置参数和初始状态
    3. on_data: 接收数据并处理
    4. generate_signals: 生成交易信号
    5. execute_orders: 执行订单
    6. risk_control: 风险控制
    7. evaluate_performance: 绩效评估
    8. on_stop: 策略停止
    """
    
    # 策略元数据，子类需要重写
    metadata: StrategyMetadata = StrategyMetadata(
        name="BaseStrategy",
        description="策略基类",
        version="1.0.0"
    )
    
    def __init__(self, params: Optional[Dict[str, Any]] = None):
        """
        初始化策略实例
        
        :param params: 策略参数
        """
        self.params = params or {}
        self.indicators = {}
        self.orders = []
        self.positions = {}
        self.signals = []
        self.performance = {}
        self.risk_metrics = {}
        self.is_initialized = False
        self.is_running = False
        
        # 初始化参数
        self._init_params()
    
    def _init_params(self):
        """
        初始化策略参数，使用默认值或传入值
        """
        for param in self.metadata.params:
            if param.name not in self.params:
                self.params[param.name] = param.default
    
    def set_params(self, params: Dict[str, Any]):
        """
        设置策略参数
        
        :param params: 策略参数
        """
        self.params.update(params)
        self._validate_params()
    
    def _validate_params(self):
        """
        验证策略参数的合法性
        """
        for param in self.metadata.params:
            if param.name in self.params:
                value = self.params[param.name]
                # 验证类型
                if param.type != "Any" and not isinstance(value, eval(param.type)):
                    raise ValueError(f"参数 {param.name} 类型错误，期望 {param.type}，实际 {type(value).__name__}")
                # 验证范围
                if param.min is not None and value < param.min:
                    raise ValueError(f"参数 {param.name} 小于最小值 {param.min}")
                if param.max is not None and value > param.max:
                    raise ValueError(f"参数 {param.name} 大于最大值 {param.max}")
    
    def initialize(self):
        """
        策略初始化
        在策略开始运行前调用，用于设置初始状态、加载数据、计算指标等
        """
        self.is_initialized = True
        self.is_running = True
        self.on_initialize()
    
    @abstractmethod
    def on_initialize(self):
        """
        子类实现的初始化方法
        """
        pass
    
    def on_data(self, data: pd.DataFrame):
        """
        接收数据并处理
        
        :param data: 输入数据，通常是OHLCV格式的DataFrame
        """
        if not self.is_initialized:
            self.initialize()
        
        # 更新指标
        self.update_indicators(data)
        
        # 生成信号
        signals = self.generate_signals(data)
        
        # 执行风险控制
        filtered_signals = self.risk_control(signals)
        
        # 执行订单
        orders = self.execute_orders(filtered_signals)
        
        # 更新绩效
        self.update_performance()
        
        return orders
    
    def update_indicators(self, data: pd.DataFrame):
        """
        更新技术指标
        
        :param data: 输入数据
        """
        self.on_update_indicators(data)
    
    @abstractmethod
    def on_update_indicators(self, data: pd.DataFrame):
        """
        子类实现的指标更新方法
        
        :param data: 输入数据
        """
        pass
    
    def generate_signals(self, data: pd.DataFrame) -> List[StrategySignal]:
        """
        生成交易信号
        
        :param data: 输入数据
        :return: 交易信号列表
        """
        signals = self.on_generate_signals(data)
        self.signals.extend(signals)
        return signals
    
    @abstractmethod
    def on_generate_signals(self, data: pd.DataFrame) -> List[StrategySignal]:
        """
        子类实现的信号生成方法
        
        :param data: 输入数据
        :return: 交易信号列表
        """
        pass
    
    def execute_orders(self, signals: List[StrategySignal]) -> List[Order]:
        """
        执行订单
        
        :param signals: 交易信号列表
        :return: 生成的订单列表
        """
        orders = self.on_execute_orders(signals)
        self.orders.extend(orders)
        return orders
    
    @abstractmethod
    def on_execute_orders(self, signals: List[StrategySignal]) -> List[Order]:
        """
        子类实现的订单执行方法
        
        :param signals: 交易信号列表
        :return: 生成的订单列表
        """
        pass
    
    def risk_control(self, signals: List[StrategySignal]) -> List[StrategySignal]:
        """
        风险控制
        对交易信号进行风险过滤
        
        :param signals: 原始交易信号列表
        :return: 过滤后的交易信号列表
        """
        return self.on_risk_control(signals)
    
    @abstractmethod
    def on_risk_control(self, signals: List[StrategySignal]) -> List[StrategySignal]:
        """
        子类实现的风险控制方法
        
        :param signals: 原始交易信号列表
        :return: 过滤后的交易信号列表
        """
        pass
    
    def update_performance(self):
        """
        更新绩效指标
        """
        self.on_update_performance()
    
    @abstractmethod
    def on_update_performance(self):
        """
        子类实现的绩效更新方法
        """
        pass
    
    def evaluate_performance(self) -> Dict[str, Any]:
        """
        绩效评估
        
        :return: 绩效评估结果
        """
        return self.on_evaluate_performance()
    
    @abstractmethod
    def on_evaluate_performance(self) -> Dict[str, Any]:
        """
        子类实现的绩效评估方法
        
        :return: 绩效评估结果
        """
        pass
    
    def stop(self):
        """
        停止策略
        """
        self.is_running = False
        self.on_stop()
    
    @abstractmethod
    def on_stop(self):
        """
        子类实现的停止方法
        """
        pass
    
    def get_metadata(self) -> StrategyMetadata:
        """
        获取策略元数据
        
        :return: 策略元数据
        """
        return self.metadata
    
    def get_positions(self) -> Dict[str, Position]:
        """
        获取当前持仓
        
        :return: 当前持仓字典
        """
        return self.positions
    
    def get_orders(self) -> List[Order]:
        """
        获取订单历史
        
        :return: 订单历史列表
        """
        return self.orders
    
    def get_signals(self) -> List[StrategySignal]:
        """
        获取信号历史
        
        :return: 信号历史列表
        """
        return self.signals
    
    def get_performance(self) -> Dict[str, Any]:
        """
        获取绩效指标
        
        :return: 绩效指标字典
        """
        return self.performance
    
    def get_risk_metrics(self) -> Dict[str, Any]:
        """
        获取风险指标
        
        :return: 风险指标字典
        """
        return self.risk_metrics
    
    def __str__(self):
        return f"{self.metadata.name} (v{self.metadata.version})"
    
    def __repr__(self):
        return self.__str__()


class BacktestStrategyBase(StrategyBase):
    """
    回测策略基类
    继承自StrategyBase，专门用于回测场景
    """
    
    def __init__(self, params: Optional[Dict[str, Any]] = None):
        """
        初始化回测策略实例
        
        :param params: 策略参数
        """
        super().__init__(params)
        self.backtest_data = None
        self.backtest_results = None
        self.initial_capital = 100000.0
        self.current_capital = self.initial_capital
        self.commission = 0.0
        self.slippage = 0.0
    
    def set_backtest_params(self, initial_capital: float = 100000.0, commission: float = 0.0, slippage: float = 0.0):
        """
        设置回测参数
        
        :param initial_capital: 初始资金
        :param commission: 佣金费率
        :param slippage: 滑点
        """
        self.initial_capital = initial_capital
        self.current_capital = initial_capital
        self.commission = commission
        self.slippage = slippage
    
    def set_backtest_data(self, data: pd.DataFrame):
        """
        设置回测数据
        
        :param data: 回测数据，OHLCV格式的DataFrame
        """
        self.backtest_data = data
    
    def run_backtest(self) -> Dict[str, Any]:
        """
        运行回测
        
        :return: 回测结果
        """
        if self.backtest_data is None:
            raise ValueError("回测数据未设置")
        
        self.initialize()
        
        # 遍历回测数据
        for index, row in self.backtest_data.iterrows():
            # 转换为OHLCV格式
            ohlcv = pd.DataFrame([row], index=[index])
            # 处理数据
            self.on_data(ohlcv)
        
        self.stop()
        
        # 计算回测结果
        self.backtest_results = self.calculate_backtest_results()
        
        return self.backtest_results
    
    @abstractmethod
    def calculate_backtest_results(self) -> Dict[str, Any]:
        """
        计算回测结果
        
        :return: 回测结果
        """
        pass


class LiveStrategyBase(StrategyBase):
    """
    实盘策略基类
    继承自StrategyBase，专门用于实盘交易场景
    """
    
    def __init__(self, params: Optional[Dict[str, Any]] = None):
        """
        初始化实盘策略实例
        
        :param params: 策略参数
        """
        super().__init__(params)
        self.exchange = None
        self.api_key = None
        self.api_secret = None
        self.passphrase = None
        self.is_connected = False
    
    def connect(self, exchange: str, api_key: str, api_secret: str, passphrase: Optional[str] = None):
        """
        连接到交易所
        
        :param exchange: 交易所名称
        :param api_key: API密钥
        :param api_secret: API密钥密码
        :param passphrase: 密码（部分交易所需要）
        """
        self.exchange = exchange
        self.api_key = api_key
        self.api_secret = api_secret
        self.passphrase = passphrase
        self.is_connected = self.on_connect()
    
    @abstractmethod
    def on_connect(self) -> bool:
        """
        子类实现的连接方法
        
        :return: 连接是否成功
        """
        pass
    
    def disconnect(self):
        """
        断开与交易所的连接
        """
        self.is_connected = not self.on_disconnect()
    
    @abstractmethod
    def on_disconnect(self) -> bool:
        """
        子类实现的断开连接方法
        
        :return: 断开连接是否成功
        """
        pass
    
    def get_account_balance(self) -> Dict[str, Any]:
        """
        获取账户余额
        
        :return: 账户余额信息
        """
        return self.on_get_account_balance()
    
    @abstractmethod
    def on_get_account_balance(self) -> Dict[str, Any]:
        """
        子类实现的获取账户余额方法
        
        :return: 账户余额信息
        """
        pass
    
    def place_order(self, order: Order) -> Dict[str, Any]:
        """
        下单
        
        :param order: 订单信息
        :return: 下单结果
        """
        return self.on_place_order(order)
    
    @abstractmethod
    def on_place_order(self, order: Order) -> Dict[str, Any]:
        """
        子类实现的下单方法
        
        :param order: 订单信息
        :return: 下单结果
        """
        pass
    
    def cancel_order(self, order_id: str) -> Dict[str, Any]:
        """
        取消订单
        
        :param order_id: 订单ID
        :return: 取消结果
        """
        return self.on_cancel_order(order_id)
    
    @abstractmethod
    def on_cancel_order(self, order_id: str) -> Dict[str, Any]:
        """
        子类实现的取消订单方法
        
        :param order_id: 订单ID
        :return: 取消结果
        """
        pass
    
    def get_order_status(self, order_id: str) -> Dict[str, Any]:
        """
        获取订单状态
        
        :param order_id: 订单ID
        :return: 订单状态
        """
        return self.on_get_order_status(order_id)
    
    @abstractmethod
    def on_get_order_status(self, order_id: str) -> Dict[str, Any]:
        """
        子类实现的获取订单状态方法
        
        :param order_id: 订单ID
        :return: 订单状态
        """
        pass
