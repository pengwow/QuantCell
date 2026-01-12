# 回测服务API数据模型

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

# 导入统一的ApiResponse模型
from common.schemas import ApiResponse


class BacktestListRequest(BaseModel):
    """
    获取回测列表请求模型
    """
    pass


class StrategyConfig(BaseModel):
    """
    策略配置详细模型
    """
    strategy_name: str = Field(
        ...,
        description="策略名称",
        example="SmaCross",
    )
    params: Dict[str, Any] = Field(
        default_factory=dict,
        description="策略参数",
        example={"n1": 10, "n2": 20},
    )
    file_path: Optional[str] = Field(
        None,
        description="策略文件路径，可选",
        example="/path/to/strategy.py",
    )


class BacktestConfig(BaseModel):
    """
    回测配置详细模型
    """
    symbols: List[str] = Field(
        default_factory=lambda: ["BTCUSDT"],
        description="交易对列表，支持多货币对同时回测",
        example=["BTCUSDT", "ETHUSDT"],
    )
    interval: str = Field(
        default="1d",
        description="时间周期",
        example="1d",
    )
    start_time: str = Field(
        ...,
        description="开始时间，格式：YYYY-MM-DD HH:MM:SS",
        example="2023-01-01 00:00:00",
    )
    end_time: str = Field(
        ...,
        description="结束时间，格式：YYYY-MM-DD HH:MM:SS",
        example="2023-12-31 23:59:59",
    )
    initial_cash: float = Field(
        default=10000.0,
        description="初始资金",
        example=10000.0,
    )
    commission: float = Field(
        default=0.001,
        description="手续费率",
        example=0.001,
    )
    exclusive_orders: bool = Field(
        default=True,
        description="是否排他订单",
        example=True,
    )


class BacktestRunRequest(BaseModel):
    """
    执行回测请求模型
    """
    strategy_config: StrategyConfig = Field(
        ...,
        description="策略配置",
        example={
            "strategy_name": "SmaCross",
            "params": {"n1": 10, "n2": 20}
        },
    )
    backtest_config: BacktestConfig = Field(
        ...,
        description="回测配置",
        example={
            "symbol": "BTCUSDT",
            "interval": "1d",
            "start_time": "2023-01-01 00:00:00",
            "end_time": "2023-12-31 23:59:59",
            "initial_cash": 10000.0,
            "commission": 0.001,
            "exclusive_orders": True
        },
    )


class BacktestAnalyzeRequest(BaseModel):
    """
    分析回测结果请求模型
    """
    backtest_id: str = Field(
        ...,
        description="回测ID",
        example="bt_1234567890",
    )


class BacktestDeleteRequest(BaseModel):
    """
    删除回测结果请求模型
    """
    backtest_id: str = Field(
        ...,
        description="回测ID",
        example="bt_1234567890",
    )


class StrategyUploadRequest(BaseModel):
    """
    上传策略文件请求模型
    """
    strategy_name: str = Field(
        ...,
        description="策略名称",
        example="SmaCross",
    )
    file_content: str = Field(
        ...,
        description="策略文件内容",
        example="from backtesting import Strategy\nfrom backtesting.lib import crossover\n\nclass SmaCross(Strategy):\n    n1 = 10\n    n2 = 20\n    \n    def init(self):\n        self.sma1 = self.I(lambda x: pd.Series(x).rolling(self.n1).mean(), self.data.Close)\n        self.sma2 = self.I(lambda x: pd.Series(x).rolling(self.n2).mean(), self.data.Close)\n    \n    def next(self):\n        if crossover(self.sma1, self.sma2):\n            self.buy()\n        elif crossover(self.sma2, self.sma1):\n            self.sell()",
    )
    description: Optional[str] = Field(
        None,
        description="策略描述，可选",
        example="基于SMA交叉的交易策略",
    )


class StrategyConfigRequest(BaseModel):
    """
    创建策略配置请求模型
    """
    strategy_name: str = Field(
        ...,
        description="策略名称",
        example="SmaCross",
    )
    params: Dict[str, Any] = Field(
        default_factory=dict,
        description="策略参数",
        example={"n1": 10, "n2": 20},
    )


class BacktestReplayRequest(BaseModel):
    """
    获取回放数据请求模型
    """
    backtest_id: str = Field(
        ...,
        description="回测ID",
        example="bt_1234567890",
    )
    step: Optional[int] = Field(
        None,
        description="回放步长，可选",
        example=10,
    )


class MetricItem(BaseModel):
    """
    回测指标项模型
    """
    name: str = Field(
        ...,
        description="指标名称",
        example="Return [%]",
    )
    value: Any = Field(
        ...,
        description="指标值",
        example=15.5,
    )
    cn_name: str = Field(
        ...,
        description="中文名称",
        example="总收益率",
    )
    en_name: str = Field(
        ...,
        description="英文名称",
        example="Total Return",
    )
    description: str = Field(
        ...,
        description="指标描述",
        example="回测期间的总收益率",
    )


class TradeItem(BaseModel):
    """
    交易记录项模型
    """
    EntryTime: str = Field(
        ...,
        description="入场时间",
        example="2023-01-01 00:00:00",
    )
    ExitTime: str = Field(
        ...,
        description="出场时间",
        example="2023-01-02 00:00:00",
    )
    Duration: str = Field(
        ...,
        description="持仓时间",
        example="1 day",
    )
    Direction: str = Field(
        ...,
        description="交易方向",
        example="多头",
    )
    EntryPrice: float = Field(
        ...,
        description="入场价格",
        example=16550.0,
    )
    ExitPrice: float = Field(
        ...,
        description="出场价格",
        example=16650.0,
    )
    Size: float = Field(
        ...,
        description="仓位大小",
        example=0.5,
    )
    PnL: float = Field(
        ...,
        description="盈亏金额",
        example=50.0,
    )
    ReturnPct: float = Field(
        ...,
        description="收益率",
        example=0.6,
    )
    Tag: Optional[str] = Field(
        None,
        description="标签，可选",
        example="SMA交叉",
    )


class EquityPoint(BaseModel):
    """
    资金曲线点模型
    """
    datetime: str = Field(
        ...,
        description="时间",
        example="2023-01-01 00:00:00",
    )
    Equity: float = Field(
        ...,
        description="权益",
        example=10000.0,
    )
    Drawdown: float = Field(
        ...,
        description="回撤",
        example=0.0,
    )


class KlineItem(BaseModel):
    """
    K线数据项模型
    """
    time: str = Field(
        ...,
        description="时间",
        example="2023-01-01 00:00:00",
    )
    open: float = Field(
        ...,
        description="开盘价",
        example=16500.0,
    )
    high: float = Field(
        ...,
        description="最高价",
        example=16600.0,
    )
    low: float = Field(
        ...,
        description="最低价",
        example=16400.0,
    )
    close: float = Field(
        ...,
        description="收盘价",
        example=16550.0,
    )
    volume: float = Field(
        ...,
        description="成交量",
        example=1000.0,
    )


class TradeSignal(BaseModel):
    """
    交易信号模型
    """
    time: str = Field(
        ...,
        description="时间",
        example="2023-01-01 00:00:00",
    )
    type: str = Field(
        ...,
        description="信号类型",
        example="BUY",
    )
    price: float = Field(
        ...,
        description="价格",
        example=16550.0,
    )
    size: float = Field(
        ...,
        description="大小",
        example=0.5,
    )
    trade_id: str = Field(
        ...,
        description="交易ID",
        example="trade_123456",
    )


class ReplayData(BaseModel):
    """
    回放数据模型
    """
    kline_data: List[KlineItem] = Field(
        ...,
        description="K线数据",
        example=[
            {
                "time": "2023-01-01 00:00:00",
                "open": 16500.0,
                "high": 16600.0,
                "low": 16400.0,
                "close": 16550.0,
                "volume": 1000.0
            }
        ],
    )
    trade_signals: List[TradeSignal] = Field(
        ...,
        description="交易信号",
        example=[
            {
                "time": "2023-01-01 00:00:00",
                "type": "BUY",
                "price": 16550.0,
                "size": 0.5,
                "trade_id": "trade_123456"
            }
        ],
    )
    equity_data: List[EquityPoint] = Field(
        ...,
        description="资金曲线数据",
        example=[
            {
                "datetime": "2023-01-01 00:00:00",
                "Equity": 10000.0,
                "Drawdown": 0.0
            }
        ],
    )


class BacktestResult(BaseModel):
    """
    回测结果响应模型
    """
    task_id: str = Field(
        ...,
        description="回测任务ID",
        example="bt_1234567890",
    )
    status: str = Field(
        ...,
        description="回测状态",
        example="completed",
    )
    message: str = Field(
        ...,
        description="回测消息",
        example="回测完成",
    )
    strategy_name: str = Field(
        ...,
        description="策略名称",
        example="SmaCross",
    )
    backtest_config: BacktestConfig = Field(
        ...,
        description="回测配置",
        example={
            "symbols": ["BTCUSDT"],
            "interval": "1d",
            "start_time": "2023-01-01 00:00:00",
            "end_time": "2023-12-31 23:59:59",
            "initial_cash": 10000.0,
            "commission": 0.001,
            "exclusive_orders": True
        },
    )
    metrics: List[MetricItem] = Field(
        ...,
        description="回测指标",
        example=[
            {
                "name": "Return [%]",
                "value": 15.5,
                "cn_name": "总收益率",
                "en_name": "Total Return",
                "description": "回测期间的总收益率"
            }
        ],
    )
    trades: List[TradeItem] = Field(
        ...,
        description="交易记录",
        example=[],
    )
    equity_curve: List[EquityPoint] = Field(
        ...,
        description="资金曲线",
        example=[
            {
                "datetime": "2023-01-01 00:00:00",
                "Equity": 10000.0,
                "Drawdown": 0.0
            }
        ],
    )
    strategy_data: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="策略数据",
        example=[],
    )


class MultiBacktestResult(BaseModel):
    """
    多货币对回测结果响应模型
    """
    task_id: str = Field(
        ...,
        description="回测任务ID",
        example="bt_1234567890",
    )
    status: str = Field(
        ...,
        description="回测状态",
        example="completed",
    )
    message: str = Field(
        ...,
        description="回测消息",
        example="多货币对回测完成",
    )
    strategy_name: str = Field(
        ...,
        description="策略名称",
        example="SmaCross",
    )
    backtest_config: BacktestConfig = Field(
        ...,
        description="回测配置",
        example={
            "symbols": ["BTCUSDT", "ETHUSDT"],
            "interval": "1d",
            "start_time": "2023-01-01 00:00:00",
            "end_time": "2023-12-31 23:59:59",
            "initial_cash": 10000.0,
            "commission": 0.001,
            "exclusive_orders": True
        },
    )
    summary: Dict[str, Any] = Field(
        ...,
        description="整体统计分析",
        example={
            "total_currencies": 2,
            "average_return": 12.5,
            "average_max_drawdown": 8.2,
            "average_sharpe_ratio": 1.8,
            "total_trades": 156,
            "overall_win_rate": 62.5
        },
    )
    currencies: Dict[str, BacktestResult] = Field(
        ...,
        description="各货币对回测结果",
        example={
            "BTCUSDT": {
                "task_id": "bt_1234567890_btcusdt",
                "status": "completed",
                "message": "回测完成",
                "strategy_name": "SmaCross",
                "backtest_config": {
                    "symbols": ["BTCUSDT"],
                    "interval": "1d",
                    "start_time": "2023-01-01 00:00:00",
                    "end_time": "2023-12-31 23:59:59",
                    "initial_cash": 10000.0,
                    "commission": 0.001,
                    "exclusive_orders": True
                },
                "metrics": [
                    {
                        "name": "Return [%]",
                        "value": 15.5,
                        "cn_name": "总收益率",
                        "en_name": "Total Return",
                        "description": "回测期间的总收益率"
                    }
                ],
                "trades": [],
                "equity_curve": [],
                "strategy_data": []
            }
        },
    )
    merged_equity_curve: List[EquityPoint] = Field(
        ...,
        description="合并后的资金曲线",
        example=[
            {
                "datetime": "2023-01-01 00:00:00",
                "Equity": 10000.0,
                "Drawdown": 0.0
            }
        ],
    )


class BacktestListItem(BaseModel):
    """
    回测列表项模型
    """
    id: str = Field(
        ...,
        description="回测ID",
        example="bt_1234567890",
    )
    strategy_name: str = Field(
        ...,
        description="策略名称",
        example="SmaCross",
    )
    created_at: str = Field(
        ...,
        description="创建时间",
        example="2023-01-01 00:00:00",
    )
    status: str = Field(
        ...,
        description="回测状态",
        example="completed",
    )
    total_return: Optional[float] = Field(
        None,
        description="总收益率，可选",
        example=15.5,
    )
